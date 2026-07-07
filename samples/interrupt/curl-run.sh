curl \
  --verbose \
  --request POST \
  'http://127.0.0.1:8000/run' \
  --header "Content-Type: application/json" \
  --data '{"initial_state":{"value":42}}'

echo
