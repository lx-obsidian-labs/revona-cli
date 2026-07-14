#!/usr/bin/env python3
"""Revona CLI — PyInstaller entry point.

This wrapper imports the ``agent`` package properly so that relative
imports inside ``agent.cli`` resolve correctly when frozen.
"""

from agent.cli import main

if __name__ == "__main__":
    main()
