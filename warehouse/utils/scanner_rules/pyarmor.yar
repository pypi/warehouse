rule pyarmor_encrypted {
  meta:
    description = "Detects PyArmor-encrypted/obfuscated Python code"
    author      = "PyPI"
    message     = "PyArmor-encrypted content is not allowed. See https://pypi.org/policy/acceptable-use-policy/ for more information."

  strings:
    // The executor call that decrypts and runs the encrypted payload.
    // Real invocations always pass __file__ as the second argument;
    // the pyarmor tool's template uses $path instead.
    $executor = "__pyarmor__(__name__, __file__,"

    // Internal runtime hooks injected into encrypted code by pyarmor.
    $pyarmor_enter  = "__pyarmor_enter__"
    $pyarmor_exit   = "__pyarmor_exit__"
    $pyarmor_assert = "__pyarmor_assert__"
    $pyarmor_bcc    = "__pyarmor_bcc__"

  condition:
    any of them
}
