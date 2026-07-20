import copy
import re
from pathlib import Path

import click
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.markdown import Markdown

from typing import Any

from . import ensure_dirs, CONFIG_PATH, DEFAULT_MODEL, BASE_URL, APP_NAME, COMPANY, REVONA_ASCII, C_ACCENT, VERSION
from .client import get_client
from .config import load_config, save_config
from .context import build_context
from .agent import (
    plan, build, run_agent, orchestrator_build,
    run_mission_engine, verify_repository, search_repository,
    _mission_queue, _capabilities, _recovery, _checkpoints, _workspaces,
    _repo_db, _semantic_search,
)
from .mission_engine import MissionPriority, MissionState, QueueStatus, CheckpointManager
from .capabilities import CapabilityDiscoveryEngine
from .recovery import RecoveryEngine
from .verification import VerificationPipeline
from .mission import Mission
from .progress import ProgressEngine
from .session import new_session_id, save_session
from .models import load_cached_models, refresh as refresh_models
from .terminal import console, print_table


def _resolve_model(override: str | None = None) -> str:
    cfg = load_config()
    return override or cfg.get("model") or DEFAULT_MODEL


def _get_client_and_model(model: str | None = None):
    return get_client(model=model)


def _expand_at_refs(text: str) -> str:
    def _replace(m):
        name = m.group(1)
        p = Path(name)
        if p.exists() and p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                return f"\n--- {name} ---\n{content}\n--- end {name} ---\n"
            except Exception:
                return m.group(0)
        return m.group(0)
    return re.sub(r'@([\w./\\_-]+(?:\.[\w]+)?)', _replace, text)


# --------------------------------------------------------------------------
# Interactive session
# --------------------------------------------------------------------------

def _start_interactive(model_override: str | None = None):
    mdl = _resolve_model(model_override)
    client, _ = _get_client_and_model(mdl)
    state_ref: dict[str, Any] = {"messages": None, "history": [], "redo_stack": [], "plan_mode": False, "session_id": new_session_id()}

    def _handle(state, text: str):
        nonlocal client, mdl

        if text.startswith("/"):
            try:
                state.add_timeline(f"Command: {text}")
                client, mdl, msgs, hist, redo, plan, handled = _handle_slash(
                    text, client, mdl, state_ref["messages"], state_ref["history"],
                    state_ref["redo_stack"], state_ref["plan_mode"]
                )
            except SystemExit:
                state.status_message = "SHUTTING DOWN"
                return
            state_ref["messages"] = msgs
            state_ref["history"] = hist
            state_ref["redo_stack"] = redo
            state_ref["plan_mode"] = plan
            if handled:
                state.add_timeline(f"Handled: {text}")
                return
        else:
            if text.lower() in ("exit", "quit", "q"):
                return

        prompt_text = _expand_at_refs(text)
        state_ref["history"].append(copy.deepcopy(state_ref["messages"] or []))
        state_ref["redo_stack"].clear()

        if state_ref["plan_mode"]:
            context = build_context()
            state.add_timeline("Planning...")
            plan(client, mdl, prompt_text, context)
            return

        state.status_message = "PROCESSING"
        state.set_agent_status("Builder", "running")
        state.add_timeline("Analysing request")
        state.add_timeline("Generating response")
        state.confidence.set("Architecture", 0.85)
        state.confidence.set("Security", 0.75)

        messages = run_agent(client, mdl, prompt_text, messages=state_ref["messages"], tui_state=state)
        state_ref["messages"] = messages
        if messages:
            content = messages[-1].get("content", "")
            if content:
                state.add_message("assistant", content)
        state.set_agent_status("Builder", "idle")
        state.status_message = "READY"
        state.knowledge_stats["Learned Today"] = state.knowledge_stats.get("Learned Today", 0) + 1
        save_session(state_ref["session_id"], messages)

    try:
        from .tui import run_cockpit
        run_cockpit(mdl, _handle)
    except Exception as e:
        console.print(f"[yellow]TUI unavailable ({e}). Using simple mode.[/]")
        from .tui import _simple_fallback
        _simple_fallback(mdl, _handle)


# --------------------------------------------------------------------------
# Slash commands (v2.0)
# --------------------------------------------------------------------------

def _handle_slash(cmd: str, client, mdl, messages, history, redo_stack, plan_mode):
    parts = cmd.strip().split()
    if not parts:
        return client, mdl, messages, history, redo_stack, plan_mode, False
    verb = parts[0].lower()

    if verb in ("/exit", "/quit", "/q"):
        raise SystemExit(0)

    if verb == "/help":
        console.print("""[bold]Slash commands:[/]
  /change model <id>   Switch model mid-session
  /models [keyword]    Browse cached models
  /plan                Toggle plan mode (no tool execution)
  /undo                Undo last assistant response
  /redo                Redo previously undone response
  /init                Index repo and cache models
  /save                Save current model as default
  /skills [keyword]    List/query available skills and blueprints
  /brain               Show repository intelligence summary
  /capabilities        Discover available system capabilities
  /search <query>      Semantic search across the repository
  /verify              Run verification pipeline
  /recovery            Show recovery history
  /mission             Show current mission status
  /queue               Show mission queue
  /workspace           List workspaces
  /checkpoints         List checkpoints
  /help                This help
  /exit, /quit         Exit
  @file                Reference a file in your prompt""")
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/capabilities":
        cde = CapabilityDiscoveryEngine()
        result = cde.discover_all()
        console.print(cde.summary())
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/search":
        query = " ".join(parts[1:])
        if not query:
            console.print("[yellow]Usage: /search <query>[/]")
            return client, mdl, messages, history, redo_stack, plan_mode, True
        results = search_repository(query)
        console.print(_semantic_search.format_results(results))
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/verify":
        console.print("[bold]Running verification pipeline...[/]")
        pipeline = VerificationPipeline()
        pipeline.discover()
        results = pipeline.run(discover=False)
        console.print(pipeline.summary)
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/recovery":
        console.print(_recovery.summary())
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/mission":
        missions = _mission_queue.all()
        if not missions:
            console.print("[yellow]No active missions.[/]")
        else:
            for m in missions[-3:]:
                console.print(m.summary())
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/queue":
        console.print(_mission_queue.summary())
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/workspace":
        if not _workspaces.all():
            console.print("[yellow]No workspaces configured.[/]")
        else:
            console.print(_workspaces.summary())
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/checkpoints":
        cps = _checkpoints.list_checkpoints()
        if not cps:
            console.print("[yellow]No checkpoints found.[/]")
        else:
            for cp in cps[-10:]:
                console.print(f"  {cp}")
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/models":
        all_models = load_cached_models()
        kw = " ".join(parts[1:]).lower() if len(parts) > 1 else ""
        if kw:
            all_models = [m for m in all_models if kw in m["id"].lower() or kw in m["owner"].lower()]
        rows = [[m["id"], m["owner"], m["category"]] for m in all_models]
        print_table(console, f"Models ({len(all_models)})", ["Model ID", "Owner", "Category"], rows)
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/plan":
        plan_mode = not plan_mode
        console.print(f"[yellow]Plan mode: {'ON' if plan_mode else 'OFF'}[/]")
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb in ("/change", "/switch"):
        if len(parts) < 3 or parts[1].lower() != "model":
            console.print("[yellow]Usage: /change model <model_id>[/]")
            return client, mdl, messages, history, redo_stack, plan_mode, True
        new_model = parts[2]
        cached = load_cached_models()
        if cached and not any(m["id"] == new_model for m in cached):
            if not Confirm.ask(f"[yellow]'{new_model}' not in cache. Use anyway?[/]"):
                return client, mdl, messages, history, redo_stack, plan_mode, True
        try:
            client, _ = get_client(model=new_model)
            console.print(f"[green]Switched to [bold]{new_model}[/][/]")
            return client, new_model, messages, history, redo_stack, plan_mode, True
        except Exception as e:
            console.print(f"[red]Failed: {e}[/]")
            return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/undo":
        if history:
            redo_stack.append(copy.deepcopy(messages or []))
            messages = history.pop()
            console.print("[yellow]Undone last response.[/]")
        else:
            console.print("[dim]Nothing to undo.[/]")
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/redo":
        if redo_stack:
            history.append(copy.deepcopy(messages or []))
            messages = redo_stack.pop()
            console.print("[yellow]Redone.[/]")
        else:
            console.print("[dim]Nothing to redo.[/]")
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/init":
        ensure_dirs()
        cfg = load_config()
        if not CONFIG_PATH.exists():
            save_config({"model": cfg.get("model", DEFAULT_MODEL)})
        key = cfg.get("api_key") or ""
        if key:
            try:
                refresh_models(key, BASE_URL)
            except Exception:
                pass
        build_context()
        _repo_db.initialize()
        _repo_db.scan_repository(Path("."))
        console.print("[green]Repo indexed (SQLite + context).[/]")
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/skills":
        from .skills import KnowledgeEngine
        ke = KnowledgeEngine()
        ke.load_all()
        kw = " ".join(parts[1:]).lower() if len(parts) > 1 else ""
        if kw:
            matched = [s for s in ke.all_skills() if kw in s.name.lower() or kw in s.description.lower()]
            for bp in ke.all_blueprints():
                if kw in bp.name.lower() or kw in bp.description.lower():
                    matched.append(bp)
            for a in ke.all_accelerators():
                if kw in a.name.lower() or kw in a.description.lower():
                    matched.append(a)
            for m in matched:
                console.print(f"  [cyan]{m.name}[/] — {m.description[:120]}")
            console.print(f"\nTotal: {len(matched)} matches")
        else:
            skills = ke.all_skills()
            bps = ke.all_blueprints()
            accs = ke.all_accelerators()
            console.print(f"[bold]Skills ({len(skills)})[/]")
            for s in skills:
                console.print(f"  [cyan]{s.name}[/] — {s.description[:100]}")
            console.print(f"\n[bold]Blueprints ({len(bps)})[/]")
            for b in bps:
                console.print(f"  [cyan]{b.name}[/] — {b.description[:100]}")
            console.print(f"\n[bold]Accelerators ({len(accs)})[/]")
            for a in accs:
                console.print(f"  [cyan]{a.name}[/] — {a.description[:100]}")
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/brain":
        from .agent import _intel
        _intel.load_all()
        ctx = _intel.brain.context_block()
        console.print(ctx)
        return client, mdl, messages, history, redo_stack, plan_mode, True

    if verb == "/save":
        cfg = load_config()
        cfg["model"] = mdl
        save_config(cfg)
        console.print(f"[green]Saved [bold]{mdl}[/] as default.[/]")
        return client, mdl, messages, history, redo_stack, plan_mode, True

    return client, mdl, messages, history, redo_stack, plan_mode, False


# --------------------------------------------------------------------------
# CLI commands (v2.0)
# --------------------------------------------------------------------------

def _print_banner():
    from rich.text import Text as RichText
    banner = RichText(REVONA_ASCII, style=f"bold {C_ACCENT}")
    console.print(banner)
    console.print(f"[bold]{APP_NAME} v{VERSION}[/]  [dim]Autonomous AI Engineering OS[/]")
    console.print(f"[dim]Built by {COMPANY}[/]")
    console.print()


@click.group(invoke_without_command=True)
@click.option("--model", "-m", help="Model to use (provider/model)")
@click.option("--no-banner", is_flag=True, help="Skip startup banner")
@click.option("--version", is_flag=True, help="Show version")
@click.pass_context
def cli(ctx, model, no_banner, version):
    """Revona CLI — Autonomous Software Engineering Operating System. Built by LX Obsidian Labs."""
    if version:
        console.print(f"Revona CLI v{VERSION}")
        return
    ensure_dirs()
    if ctx.invoked_subcommand is None:
        if not no_banner:
            _print_banner()
        _start_interactive(model_override=model)


# --------------------------------------------------------------------------
# v1.x compatibility commands
# --------------------------------------------------------------------------

@cli.command()
@click.argument("prompt", nargs=-1, required=True)
@click.option("--model", "-m", help="Model override")
def run(prompt, model):
    """Non-interactive: execute a prompt and exit."""
    mdl = _resolve_model(model)
    client, _ = _get_client_and_model(mdl)
    text = _expand_at_refs(" ".join(prompt))
    run_agent(client, mdl, text)


@cli.command()
@click.argument("prompt", nargs=-1, required=True)
@click.option("--model", "-m", help="Model override")
@click.option("--yes", "-y", is_flag=True, help="Skip approval prompt")
def build_cmd(prompt, model, yes):
    """Plan > approve > execute a full project (v1.x compat)."""
    mdl = _resolve_model(model)
    client, _ = _get_client_and_model(mdl)
    request = " ".join(prompt)
    console.print("[bold]Building context...[/]")
    context = build_context()

    console.print("\n[bold yellow]--- PHASE 1: PLAN ---[/]")
    plan_messages = plan(client, mdl, request, context)
    if not yes and not Confirm.ask("\nApprove this plan and start building?"):
        console.print("[yellow]Cancelled.[/]")
        return

    console.print("\n[bold yellow]--- PHASE 2: BUILD ---[/]")
    progress = ProgressEngine("Build")
    mission = orchestrator_build(client, mdl, request, progress)
    save_session(new_session_id(), {"request": request, "mission_id": mission.id})
    console.print(f"[green]Done.[/]  Tasks: {mission.status_counts()}")


# --------------------------------------------------------------------------
# v2.0 mission command
# --------------------------------------------------------------------------

@cli.command()
@click.argument("request", nargs=-1, required=True)
@click.option("--model", "-m", help="Model override")
@click.option("--yes", "-y", is_flag=True, help="Auto-approve plan")
@click.option("--priority", "-p", type=click.Choice(["low", "normal", "high", "critical"]), default="normal")
def mission(request, model, yes, priority):
    """[v2.0] Start an engineering mission with the full state machine lifecycle."""
    mdl = _resolve_model(model)
    client, _ = _get_client_and_model(mdl)
    request_text = " ".join(request)
    prio_map = {"low": MissionPriority.LOW, "normal": MissionPriority.NORMAL,
                "high": MissionPriority.HIGH, "critical": MissionPriority.CRITICAL}

    console.print(f"[bold]Starting mission:[/] {request_text[:80]}...")
    console.print(f"[dim]Priority: {priority}[/]")

    mission = run_mission_engine(
        client, mdl, request_text,
        priority=prio_map[priority],
        auto_approve=yes,
    )

    if mission.state == MissionState.MISSION_COMPLETE:
        score = mission.engineering_score()
        console.print(f"\n[bold green]Mission Complete![/]  Score: {score['overall']:.0f}/100")
        console.print(f"[dim]{mission.summary()}[/]")
    elif mission.state == MissionState.FAILED:
        console.print(f"\n[bold red]Mission Failed:[/] {mission.error}")
    elif mission.state == MissionState.CANCELLED:
        console.print("\n[yellow]Mission cancelled by user.[/]")


# --------------------------------------------------------------------------
# v2.0 utility commands
# --------------------------------------------------------------------------

@cli.command()
def discover():
    """[v2.0] Discover available system capabilities."""
    cde = CapabilityDiscoveryEngine()
    result = cde.discover_all()
    console.print(cde.summary())


@cli.command()
@click.argument("query", nargs=-1, required=True)
@click.option("--top", "-k", default=15, help="Number of results")
def search(query, top):
    """[v2.0] Semantic code search across the repository."""
    q = " ".join(query)
    results = search_repository(q, top_k=top)
    console.print(_semantic_search.format_results(results))


@cli.command()
@click.option("--root", default=".", help="Repository root")
def verify(root):
    """[v2.0] Run the verification pipeline on the repository."""
    console.print("[bold]Running verification pipeline...[/]")
    pipeline = VerificationPipeline(root)
    pipeline.discover()
    results = pipeline.run(discover=False)
    console.print(pipeline.summary)
    if pipeline.all_passed:
        console.print("[green]All checks passed.[/]")
    else:
        console.print("[yellow]Some required checks failed.[/]")


@cli.command()
def recovery():
    """[v2.0] Show recovery engine history."""
    console.print(_recovery.summary())


@cli.command()
def queue():
    """[v2.0] Show the mission queue."""
    console.print(_mission_queue.summary())


@cli.command()
@click.argument("name", required=False)
@click.argument("path", required=False)
def workspace(name, path):
    """[v2.0] Manage workspaces: `revona workspace`, `revona workspace list`, `revona workspace add NAME PATH`."""
    if name == "list":
        console.print(_workspaces.summary())
    elif name == "add":
        if path:
            _workspaces.add(name, path)
            console.print(f"[green]Added workspace '{name}' → {path}[/]")
        else:
            console.print("[yellow]Usage: revona workspace add NAME PATH[/]")
    elif name and path:
        _workspaces.add(name, path)
        console.print(f"[green]Added workspace '{name}' → {path}[/]")
    elif name:
        if _workspaces.activate(name):
            console.print(f"[green]Switched to workspace '{name}'[/]")
        else:
            console.print(f"[red]Workspace '{name}' not found.[/]")
    else:
        console.print(_workspaces.summary())


@cli.command()
def checkpoints():
    """[v2.0] List available checkpoints."""
    cps = _checkpoints.list_checkpoints()
    if not cps:
        console.print("[yellow]No checkpoints found.[/]")
    else:
        console.print(f"[bold]Checkpoints ({len(cps)}):[/]")
        for cp in cps[-20:]:
            console.print(f"  {cp}")


@cli.command()
@click.argument("source", required=True)
@click.argument("name", required=True)
def install(source, name):
    """[v2.0] Install a plugin from a path."""
    from .plugin_sdk import PluginSDK
    sdk = PluginSDK()
    sdk.initialize()
    if sdk.install(name, source):
        console.print(f"[green]Installed plugin '{name}'.[/]")
    else:
        console.print(f"[red]Failed to install '{name}' from {source}.[/]")


# --------------------------------------------------------------------------
# Original v1.x commands
# --------------------------------------------------------------------------

@cli.command()
@click.argument("set_args", nargs=-1)
@click.option("--key", help="Set NVIDIA_API_KEY (prefer env var)")
@click.option("--model", "-m", help="Set default model ID")
@click.option("--list-models", is_flag=True, help="List cached models")
def config(set_args, key, model, list_models):
    """View or set configuration.

    Usage:
        revona config                          Show current config
        revona config --model deepseek-v4-pro  Set model
        revona config set model NAME           Set model (shorthand)
        revona config set api_key KEY          Set API key
        revona config --list-models            List cached models
    """
    if list_models:
        models = load_cached_models()
        if not models:
            console.print("[yellow]Run `revona refresh` first.[/]")
            return
        for m in models:
            console.print(f"  [cyan]{m['id']}[/]  ({m['category']})")
        console.print(f"\nTotal: {len(models)}")
        return

    cfg = load_config()
    changed = False

    # Normalize: strip literal "set" keyword if present
    args = list(set_args)
    if args and args[0].lower() == "set":
        args = args[1:]

    # Handle "set key value" or just "key value" syntax
    if len(args) >= 2:
        set_key = args[0].lower()
        set_value = args[1]
        if set_key == "model":
            cached = load_cached_models()
            if cached and not any(m["id"] == set_value for m in cached):
                if not Confirm.ask(f"[yellow]'{set_value}' not in cache. Use anyway?[/]"):
                    return
            cfg["model"] = set_value
            save_config(cfg)
            console.print(f"[green]OK[/] Default set to [bold]{set_value}[/]")
            changed = True
        elif set_key in ("api_key", "key"):
            import os
            os.environ["NVIDIA_API_KEY"] = set_value
            console.print(f"[green]OK[/] API key set (use NVIDIA_API_KEY env for persistence)")
            changed = True
        else:
            console.print(f"[yellow]Unknown config key: '{set_key}'. Available: model, api_key[/]")
    elif len(args) == 1:
        console.print(f"[yellow]Usage: revona config set {args[0]} <value>[/]")

    if key:
        console.print("[yellow]Set the env var instead:[/]")
        console.print(f"  $env:NVIDIA_API_KEY='{key}'  (PowerShell)")
        console.print(f"  export NVIDIA_API_KEY='{key}'  (bash)")

    if model:
        cached = load_cached_models()
        if cached and not any(m["id"] == model for m in cached):
            if not Confirm.ask(f"[yellow]'{model}' not in cache. Use anyway?[/]"):
                return
        cfg["model"] = model
        save_config(cfg)
        console.print(f"[green]OK[/] Default set to [bold]{model}[/]")
        changed = True

    if not changed and not args:
        console.print(f"Model:  [bold]{cfg.get('model')}[/]")
        status = "set" if cfg.get("api_key") else "not set"
        console.print(f"API key: {status} (use NVIDIA_API_KEY env)")
        console.print(f"Cache:  {len(load_cached_models())} models")


@cli.command()
@click.option("--search", "-s", help="Filter by keyword")
@click.option("--category", "-c", help="Filter by category")
def models(search, category):
    """List cached models from NVIDIA NIM."""
    all_models = load_cached_models()
    if not all_models:
        console.print("[yellow]Run `revona refresh` first.[/]")
        return
    if category:
        all_models = [m for m in all_models if m["category"] == category]
    if search:
        q = search.lower()
        all_models = [m for m in all_models if q in m["id"].lower() or q in m["owner"].lower()]
    rows = [[m["id"], m["owner"], m["category"]] for m in all_models]
    print_table(console, f"Models ({len(all_models)})", ["Model ID", "Owner", "Category"], rows)


@cli.command()
def refresh():
    """Refresh cached model list from NVIDIA."""
    cfg = load_config()
    key = cfg.get("api_key") or ""
    if not key:
        console.print("[yellow]NVIDIA_API_KEY not found.[/]")
        return
    try:
        models = refresh_models(key, BASE_URL)
        console.print(f"[green]Cached {len(models)} models.[/]")
    except Exception as e:
        console.print(f"[red]{e}[/]")


@cli.command()
def plan_cmd():
    """[deprecated] Use 'revona plan' via interactive session."""
    console.print("[yellow]Use /plan inside the interactive session.[/]")


def main():
    cli()


if __name__ == "__main__":
    main()
