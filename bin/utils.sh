# Buildpack Indented line.
puts-line() {
  echo "       $@"
}

# Buildpack Steps.
puts-step() {
  echo "-----> $@"
}
