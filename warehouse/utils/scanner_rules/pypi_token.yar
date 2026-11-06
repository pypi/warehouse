rule secrets_pypi_token
{
  meta:
    description = "Detects PyPI API tokens exposed in source code."
    author = "Kamil Mankowski"
    message = "We have detected a PyPI API token exposed in the uploaded file. Publishing it would allow anyone to perform actions on your behalf. For your own security, please revoke the token immediately. See https://pypi.org/help/#compromised-token for additional help."

  strings:
    // Regex adapted from trufflehog's PyPI token detector
    // Intentionally not derived from the official Token format definition to spare unnecessary matches.
    // Pre-computed head ensures we match actual pypi.org tokens
    // https://github.com/trufflesecurity/trufflehog/blob/05a583290be8c8f79852eb8741f5042920b47d00/pkg/detectors/pypi/pypi.go#L28
    $pypi_token = /pypi-AgEIcHlwaS5vcmcCJ[a-zA-Z0-9-_]{150,157}/

    // If we come across test tokens in use we should exclude
    // it culd be done by adding a string like this and uncommenting the condition below.
    // $test_token = "pypi-AgEIcHlwaS5vcmcCJxxx"

  condition:
    $pypi_token
    // If we want to allow some test-only tokens, we can use:
    // and for all i in (1 .. #pypi_token) : (
    // 	not $test_token at @pypi_token[i]
    // )
}
