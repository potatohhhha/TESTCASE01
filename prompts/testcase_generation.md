You are generating tests for a C project. Return one strict JSON object and no Markdown fences.

The JSON schema is:
{"testcases":[{"testcase_id":"TC001","requirement_id":"REQ001","description":"...","inputs":{},"expected":{},"unresolved":false}],"test_code":"complete CMocka C program"}

Rules:
- Derive expected values only from the requirements, never by copying observed implementation output.
- Give every case a unique testcase_id and identify its requirement.
- testcase_id must be a valid C identifier such as TC001. For every resolved case,
  create exactly one registered CMocka test function whose function name contains
  that exact testcase_id (for example, test_TC001_below_min). This is required for
  JUnit result traceability.
- If an expected result cannot be determined, set unresolved=true, explain why in expected, and do not add a fabricated assertion for it.
- test_code must be complete: includes, test functions, assertions, registration, and main.
- Include <stdarg.h>, <stddef.h>, and <setjmp.h> before <cmocka.h>, as required by CMocka.
- Do not name any helper `run_test`; that name is reserved by a CMocka compatibility macro.
- Every test function must explicitly mark an unused state argument with (void)state.
- Do not modify or embed replacements for production source files.

REQUIREMENTS:
{{ requirements }}

SOURCE FILES:
{{ sources }}

HEADER FILES:
{{ headers }}

COMPILER CONFIGURATION:
{{ compiler }}

TEST STYLE:
{{ test_style }}

Test-style rules:
- For `function`, test public functions through their headers as ordinary CMocka unit tests.
- For `direct_main`, the build system compiles each production source separately with
  `-Dmain=codeflaws_main` and links it into the CMocka executable. Declare
  `extern int codeflaws_main(int argc, char *argv[]);` and call it directly in the same process.
  Feed scanf/stdin using `fmemopen()` and capture printf/stdout using `open_memstream()`.
  Save stdin/stdout before the call, flush the captured stdout, restore both streams immediately
  after the call, and close/free all memory streams. Perform CMocka assertions only after restoring
  stdin/stdout. Do not use fork(), pipe(), dup2(), execl()/execv(), waitpid(), system(), popen(),
  PROGRAM_UNDER_TEST, a shell, files from the benchmark test suite, or the accepted solution.
  Do not include the production .c file. Each test may call codeflaws_main at most once.
  Compare output exactly as required by the problem while tolerating only insignificant trailing
  whitespace. Actually terminate or length-limit both strings when trimming; do not merely decrement
  an unused length variable.
- For `console`, the source is an immutable standalone stdin/stdout program with its own main.
  Do not include, rewrite, rename, or call its main. Generate a complete POSIX CMocka black-box
  test program that reads the executable path from the PROGRAM_UNDER_TEST environment variable.
  Each test must launch a fresh child with fork(), connect stdin and stdout using pipe() and dup2(),
  invoke the executable directly with execl()/execv(), collect stdout, and wait with waitpid().
  Do not use system(), popen(), a shell, files from the benchmark test suite, or the accepted solution.
  Compare output according to the problem statement while tolerating insignificant trailing whitespace.
