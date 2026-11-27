# CoreTests: the dotnet fast loop for PainterIO.Core

Runs the pure C# Core (`Assets/Scripts/Core`) and its NUnit tests (`Assets/Tests/EditMode/Core`) outside Unity, with no
Unity lock (contract 2.2). The same test files also run inside Unity (EditMode) as part of `PainterIO.Tests.EditMode`.

| File | Role |
|---|---|
| `PainterIO.Core.csproj` | `netstandard2.1`, compiles `../../Assets/Scripts/Core/**/*.cs` (same as `PainterIO.Core.asmdef`) |
| `PainterIO.CoreTests.csproj` | `net9.0`, NUnit 3.14 + NUnit3TestAdapter + Microsoft.NET.Test.Sdk, compiles `../../Assets/Tests/EditMode/Core/**/*.cs`; assembly named `PainterIO.Tests.EditMode` like the Unity test assembly |
| `Directory.Build.props` | artifacts output (isolation), C# 9, no implicit usings, nullable off, no default globbing |

All commands run from the project root (`Brainstorming/games/painter_io`) in PowerShell. Do not use Git Bash.

## Commands

Full run (do this before you finish):

```powershell
dotnet test tools/CoreTests/PainterIO.CoreTests.csproj --artifacts-path tools/CoreTests/.art/<package> -v q
```

Filtered run while iterating (NUnit adapter filter syntax; `~` means "contains"):

```powershell
dotnet test tools/CoreTests/PainterIO.CoreTests.csproj --artifacts-path tools/CoreTests/.art/<package> -v q --filter "FullyQualifiedName~R13b_"
dotnet test tools/CoreTests/PainterIO.CoreTests.csproj --artifacts-path tools/CoreTests/.art/<package> -v q --filter "FullyQualifiedName~C1_|FullyQualifiedName~C2_"
dotnet test tools/CoreTests/PainterIO.CoreTests.csproj --artifacts-path tools/CoreTests/.art/<package> -v q --filter "FullyQualifiedName~PainterIO.Tests.GeoTests"
```

Useful extras:

- See failure messages and stack traces: add `--logger "console;verbosity=normal"`.
- Rerun without rebuilding: add `--no-build`.
- List the discovered tests: add `--list-tests`.
- `-v q` hides the build log; drop it to see compiler errors in full.

A summary line `Passed! - Failed: 0, Passed: N ...` with N > 0 is the only green. A run of zero tests proves nothing.

## Artifacts path rule (parallel agents)

Every agent passes its OWN artifacts root: `--artifacts-path tools/CoreTests/.art/<package>` (for example `.art/grid`,
`.art/trail`, `.art/sim`, `.art/bots`, `.art/auditor`). All obj and bin output of both projects then lives under that
folder, so two agents building at the same time never share an intermediate file. Without the option, output goes to
`tools/CoreTests/.art/default`, which IDE design-time builds also use: never rely on it while other agents work.
`tools/CoreTests/.art/` is git-ignored.

Verified on this machine (SDK 9.0.321): `dotnet test --artifacts-path` is supported, the relative path is resolved from
the current directory, and two concurrent full runs with different paths both pass.

Every `dotnet build` compiles ALL Core files, including files other agents are editing. If the build fails in a file you
do not own, that agent is mid-edit: wait (`Start-Sleep 60`) and retry; never touch it.

## Rules for code and tests (they also compile inside Unity)

- C# 9 / .NET Standard 2.1 (enforced here by `LangVersion 9.0`): no `record struct`, no file-scoped namespaces, no global
  usings, no `init` setters, no `System.Numerics.BitOperations`. Write every `using` explicitly (implicit usings are off,
  as in Unity).
- Core: namespace `PainterIO.Core`, no `UnityEngine`. Tests: namespace `PainterIO.Tests`, only NUnit + PainterIO.Core.
- Unity ships NUnit 3.5 while this project uses 3.14: use only `[Test]`, `[TestCase]`, `[SetUp]`, `[TearDown]`,
  `[TestCaseSource]`, `Assert.That`, `Assert.AreEqual`, `Assert.AreNotEqual`, `Assert.IsTrue`, `Assert.IsFalse`,
  `Assert.IsNull`, `Assert.IsNotNull`, `Assert.AreSame`, `Assert.Throws`, `Assert.Fail`, `Is.EqualTo(...).Within(...)`.
  Never `Assert.Multiple`, `Assert.Positive`, `Assert.Zero` or other post-3.5 additions.
- Test names start with the contract test id (`C1_`, `R13b_`, `S4_`, `GR-Edge` as `GREdge_` ...).
- Code that must differ inside Unity uses `#if UNITY_5_3_OR_NEWER` (defined only in Unity).

## Full verification

`pwsh -NoProfile -File tools/verify.ps1` runs the dotnet step (counts read from a TRX report) and the Unity EditMode step
(through `tools/unity.ps1`, counts read from the JUnit report, zero tests refused). `-Steps dotnet` runs one step,
`-List` lists them, `-Agent <name>` names the lock holder and the artifacts folder. Summary in `docs/verify_last.txt`.
