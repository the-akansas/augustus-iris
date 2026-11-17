Creator source recovery, review129 (2026-11-10)

13 C# files were recovered from the prior local r100 handoff. r110 integration
was reapplied. CreatorBriefing.cs was recovered from the installed r127 assembly
using ILSpy 8.2.0.7535, C#5 output. Before fixes, rebuilding these sources in the
original compile order produced exactly identical whole-module decompilation
to the installed r127 creator. This is source reconstruction, not the original
text of the missing briefing file.

See evidence/review129/recovery-provenance.json for source paths and SHA256.
ILSpy is not required for future builds.

Build from package root:
  Augustus\runtime\python.exe -B -X utf8 handoff.py build-creator

Uses Windows .NET Framework64 v4.0.30319 csc.exe, x64 WinExe, and
System.Windows.Forms.dll, System.Drawing.dll, System.Web.Extensions.dll.
Output: build/local/Augustus-Scenario-Creator.exe (does not install automatically).
The online player limit is generated from Augustus/multiplayer_limits.py into
build/local/CreatorLimits.cs. Scenario schema validation remains authoritative.

Changes after parity check: replace the stale four-player launch cap with the
shared online limit; update player-count and JSON/mapx sharing guidance; add
--runtime-check <project.json> for data-only validation (does not launch a game).
The original editor, emperor favor, personal gifts and game rules are unchanged.
