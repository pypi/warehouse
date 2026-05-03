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
		// https://github.com/trufflesecurity/trufflehog/blob/main/pkg/detectors/pypi/pypi.go
		$pypi_token = /pypi-AgEIcHlwaS5vcmcCJ[a-zA-Z0-9-_]{150,157}/

		// TODO: look if there are test tokens in use we should exclude
		// $test_token = "pypi-AgEIcHlwaS5vcmcCJxxx"

	condition:
		$pypi_token
		// If we want to allow some test-only tokens, we can use:
		// and for all i in (1 .. #pypi_token) : (
		// 	not $test_token at @pypi_token[i]
		// )
}
