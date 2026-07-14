# Docker Verification Checklist

- [ ] Image builds successfully (`docker build .`)
- [ ] Image size optimized (< 500MB for Node apps)
- [ ] No secrets in layers
- [ ] Health check configured
- [ ] Non-root user
- [ ] .dockerignore present
- [ ] Compose services connect properly
