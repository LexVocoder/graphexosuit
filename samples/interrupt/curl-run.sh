curl \
  -v \
  -X POST \
  'http://127.0.0.1:8000/run' \
  -H "Content-Type: application/json" \
  -d '{"initial_state":{"value":42}}'

echo
