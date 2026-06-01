# Contributing

StorageOps is a Pi Coding Agent extension + skill pack. Contributing is simple — you don't need to write Python agent code.

## How to Contribute

### Add a New Diagnostic Domain

1. Create a new directory under `skills/`:
   ```bash
   mkdir -p skills/storageops-<new-domain>/references
   ```

2. Write `skills/storageops-<new-domain>/SKILL.md`:
   ```yaml
   ---
   name: storageops-new-domain
   description: >
     Brief description of the diagnostic domain.
   maturity: alpha
   mode: light_heavy
   trigger_keywords:
     - keyword1
     - keyword2
   recommended_tools:
     - scan_secrets
     - detect_domain
     - search_memory
   ---

   # Diagnosis Title

   ## When to Use This Skill
   ...

   ## Light Diagnosis
   ...

   ## Deep Diagnosis
   ...
   ```

3. Test with Pi:
   ```bash
   pi --skills ./skills "test scenario"
   ```

No code changes needed.

### Improve the Extension

Edit `.pi/extensions/storageops.ts` to add or improve tools. Tools run inline in TypeScript:

```typescript
pi.registerTool({
  name: "my_tool",
  label: "My Tool",
  description: "What this tool does",
  parameters: Type.Object({ input: Type.String() }),
  async execute(_toolCallId, params) {
    return { content: [{ type: "text", text: JSON.stringify({ result: params.input }) }] };
  },
});
```

### Update Skills

Edit existing SKILL.md files:
- Add or improve trigger keywords
- Refine diagnostic instructions
- Add reference materials

### Project Structure

```
storageops/
├── .pi/extensions/storageops.ts   ← Pi extension (edit to add tools)
├── skills/                        ← Skill packs (edit to add domains)
│   └── storageops-*/SKILL.md
├── docs/                          ← Documentation
├── scripts/                       ← Utility scripts
├── AGENTS.md                      ← Agent instructions
├── README.md
└── CONTRIBUTING.md
```

### Setup

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops
npm install -g @earendil-works/pi-coding-agent   # if not already installed
```

### Testing

```bash
# Test a skill
pi --skills ./skills "test question for the skill"

# Test with golden cases
cd skills/storageops-eval-golden-cases/cases/<case-name>
cat input/* | pi --skills ../../../ "diagnose this"
```

### Commit Guidelines

- Keep commits small and focused
- Prefix with `feat:`, `fix:`, `docs:`, or `skill:` for skill pack changes
- Update CHANGELOG.md for user-facing changes

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
