rule sourcedefender_encrypted {
  meta:
    description = "Detects SourceDefender-encrypted Python code (.pye)"
    author      = "PyPI"
    message     = "SourceDefender-encrypted content is not allowed. See https://pypi.org/policy/acceptable-use-policy/ for more information."

  strings:
    $begin = "---BEGIN PYE FILE---"
    $end   = "---END PYE FILE---"

  condition:
    // We want to detect SourceDefender only in the dedicated .pye files.
    // Empty filenames means initial batch scan.
    (filename == "" or filename matches /\.pye$/i) and
    all of them
}
