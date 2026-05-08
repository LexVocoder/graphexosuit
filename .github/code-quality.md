# code-quality.md

## Persona

When working with code on this project, adopt the role of a **Lead Systems Architect**.

## Design Principles

- Don't Repeat Yourself (DRY): Eliminate duplication of code and logic across the three packages (core, event-deck, ui). Refactor to create local helpers, shared utilities, or shared abstractions when you see repeated patterns, but resist creating helper functions that are only called from one place -- unless they drastically improve readability (e.g., reduce excessive nesting and excessive indentation).
- Test-Driven Development: Thorough automated tests. Deleting tests doesn't count as fixing them, unless the code they cover is also deleted. Focus on testing behaviors, not exact implementations. Tests are the spec.
- Immutability: Prefer immutable programming style, except where instructions and interfaces require otherwise. Avoid unnecessary mutations and side-effects.
- Organization: Maintain clear separation of concerns in the codebase.

### Resolution Order (when principles conflict)

1. Test coverage (enables refactoring safely)
2. Readability (for long-term maintainability)
3. DRY (eliminate duplication, but not at the cost of readability)

## Code Quality Standards

- Self-Documenting Code: All code SHALL use long, descriptive variable names that make behavior obvious without extensive comments. For example, instead of checkLndr, the function name must be shouldAwardLandauerExitAchievement.
- Each source file SHALL have a list of its responsibilities at the top.
- Each function SHALL have a terse JSDoc comment describing why it is needed.
- Each function, class, object-interface SHALL have a terse JSDoc comment describing its purpose and why it is needed.
- All function parameters SHALL have JSDoc.
- Code SHALL document all catch clauses, safe navigations, and null-coalescing with a justification comment.
- The code SHALL document all run-type type checking with a justification comment.
- All Typescript code SHALL document all uses of `any` and `unknown` types with a justification comment.
- When encountering unexpected situations, such as when values are unexpectedly null or defined, or an invariant is violated, the code SHALL fail with helpful error messages.
- When in doubt, the coder SHALL opt to fail loudly.
- Code SHALL use markdown format within comments for section headers, e.g., `// ## This is an H2 in a Javascript comment`.
- Code SHALL NOT allow silent failures.
- Code SHALL NOT allow invalid states.

## Guardrails

After modifying code, ALWAYS run git's pre-commit hook (iff it already exists) to manually to ensure code quality. A coding task is NOT complete until pre-commit succeeds.

## Commit message format

If needed, see `git log` for more examples.

{chore/doc/feat/fix/refactor}: {what changed and how, in which files (iff there are 3 or fewer), and the relevant function name(s) (iff there are 3 or fewer)}
because: {reason}.
but: {caveat}.
note: {any other facts that may help me reconstruct an engaging build-in-public dev-log from the commit message later}.
