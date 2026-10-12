#ifndef LLM_AUTOTEST_CMOCKA_COMPAT_H
#define LLM_AUTOTEST_CMOCKA_COMPAT_H

/* CMocka expects these standard types to be declared by its caller. */
#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>

/* Avoid a collision with a common generated black-box helper name. */
#ifdef run_test
#undef run_test
#endif

#endif
