# TypeScript / React profile — slice-builder

Concrete idioms for a **frontend** slice — one React component, one hook, or one TS module (NOT a whole page). Apply wherever the core says *"per your language profile."*

**Test runner.** `vitest` + **React Testing Library** (`@testing-library/react`) for components; plain `vitest` for hooks/utils. Show `vitest` (e.g. `npx vitest run <file>`) output at every RED / GREEN / REFACTOR transition. Test a component through what the user **sees and does** — query by role / label / text, fire events — never by reading internal state. Skeleton "it compiles" check: `tsc --noEmit` succeeds and the test file collects under `vitest`.

**Type checker / strictness.** `tsc --noEmit` clean under `strict: true`. No `any`, no `@ts-ignore`. Props and return types fully typed.

**Value / data shapes.**
- `interface` / `type` → internal props and local shapes.
- **`zod` schema + `z.infer<typeof Schema>`** → cross-boundary data (API responses, form input, anything from the network or the user). Parse at the boundary (`Schema.parse(data)`); pass typed objects inward. zod is the TS analogue of Pydantic.

**Dependency injection — the React form.** Props ARE injection. Data, callbacks (`onSubmit`, `onUploaded`), and clients come IN as props (or via a context provider the parent supplies) — never `fetch` or construct a client inside the component. A hook takes its dependencies as arguments. This is what lets a test render the component with fakes.

**Skeleton form.** The component shell returning a minimal element (or `return null`); a named props `interface` with fields + types; a top comment stating what it renders and what it explicitly does NOT. For a hook: the signature + a typed return shape, body `throw new Error("slice in progress")`.

**Paranoid-SRP — the React form.** ONE component = ONE responsibility. A component that fetches AND transforms AND renders AND handles a form becomes a small **container** (owns data/state via a hook) composing **presentational** children (render given props), plus a **custom hook** for the logic.
NOT this:
```tsx
function UploadPanel({ caseId }: { caseId: string }) {
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState<string>()
  // fetch existing + validate + upload + render list + render dropzone + render errors…
}
```
THIS:
```tsx
function UploadPanel({ caseId }: UploadPanelProps) {        // container = orchestrate
  const { items, error, upload } = useUploads(caseId)       // logic lives in a hook
  return (
    <>
      <Dropzone onDrop={upload} />                           {/* one responsibility */}
      <UploadList items={items} />                           {/* one responsibility */}
      {error && <ErrorBanner message={error} />}             {/* one responsibility */}
    </>
  )
}
```
Each child renders one thing; the hook owns the logic; the container only composes. Sub-components + a hook for SRP are NOT premature abstraction (rule 5 is about generic Providers / HOCs / render-props for a single use).

**No premature abstraction (React-specific).** No generic `<Provider>` / context for one consumer, no HOC or render-prop indirection, no compound-component machinery, no state-management library for local state, no premature `forwardRef` / generics. One component, one use → write it directly.

**Per-unit test heuristics** (extending the core's rule 6):
- **Presentational component** (renders from props, no logic): 1–2 — renders the key content given props + one conditional-render branch (e.g. shows the error banner when `error` is set).
- **Interactive component**: renders + one test per user-action outcome (click / submit / type → the expected callback call or rendered change) + one per conditional render branch.
- **Data states**: if it has loading / success / error states, one test each (the three).
- **Custom hook**: initial return + one test per state transition (RTL `renderHook` + `act`).

**Smoke convention.** No script — **run the app and verify in the browser**. Start the dev server (`npm run dev` or the project's dev command), then give an EXPLICIT instruction, e.g.: *"Open http://localhost:5173/cases/123, drop a PDF on the upload box, confirm it appears in the list with a green check and the filename. Reply DONE or FAIL."* If the project already has Playwright / Cypress, an e2e smoke is fine — but manual browser verification is the default.
