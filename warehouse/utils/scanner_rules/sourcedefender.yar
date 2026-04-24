rule sourcedefender_encrypted {
  meta:
    description = "Detects SourceDefender-encrypted Python code (.pye)"
    author      = "PyPI"
    message     = "SourceDefender-encrypted content is not allowed. See https://pypi.org/policy/acceptable-use-policy/ for more information."

  strings:
    $begin = "---BEGIN PYE FILE---"
    $end   = "---END PYE FILE---"

  condition:
    all of them
}
