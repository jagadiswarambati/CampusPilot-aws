#!/usr/bin/env bash
# One-command deploy: backend (AWS SAM) + frontend (AWS Amplify Hosting manual deployment).
# Requires: AWS CLI (configured), AWS SAM CLI, zip, curl.
#   AWS_REGION=ap-south-1  STACK_NAME=campuspilot  USE_BEDROCK=false  ./scripts/deploy.sh
set -Eeuo pipefail
cd "$(dirname "$0")/.."

REGION="${AWS_REGION:-ap-south-1}"
STACK="${STACK_NAME:-campuspilot}"
USE_BEDROCK="${USE_BEDROCK:-false}"

say()  { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
trap 'fail "A command failed on line $LINENO: $BASH_COMMAND"' ERR
trap 'rm -rf .build' EXIT  # never leave the temporary build folder behind

for tool in aws sam zip curl; do
  command -v "$tool" > /dev/null || fail "'$tool' is not installed. See 'Prerequisites' in README.md."
done
[[ "$USE_BEDROCK" == "true" || "$USE_BEDROCK" == "false" ]] || fail "USE_BEDROCK must be 'true' or 'false' (got '$USE_BEDROCK')."
ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2> /dev/null) \
  || fail "AWS credentials are missing or expired. Run 'aws configure' (or 'aws sso login') and try again."
echo "Account $ACCOUNT | region $REGION | stack $STACK | Bedrock enabled: $USE_BEDROCK"
[[ "$USE_BEDROCK" == "true" ]] && warn "Bedrock is billed per token (it uses your credits). The app works without it."

say "1/5 Building and deploying the backend (SAM)"
sam build
sam deploy --stack-name "$STACK" --region "$REGION" --resolve-s3 \
  --capabilities CAPABILITY_IAM --no-confirm-changeset --no-fail-on-empty-changeset \
  --parameter-overrides "UseBedrock=$USE_BEDROCK"

output() {
  aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
API_URL=$(output ApiUrl)
LOG_GROUP=$(output LogGroupName)
[[ "$API_URL" == https://* ]] || fail "Could not read ApiUrl from the stack outputs. Check the CloudFormation console."

say "2/5 Smoke-testing the API (API Gateway, Lambda, IAM, DynamoDB seeding and seat-booking transactions)"
OK=""; OUT=""
for _ in 1 2 3; do
  if OUT=$(curl -sS --max-time 25 -X POST "$API_URL/plan" -H 'Content-Type: application/json' \
      -d '{"text":"30 minutes, 10 pages printed"}' 2>&1) && [[ "$OUT" == *'"feasible"'* ]]; then OK=1; break; fi
  sleep 3
done
[[ -n "$OK" ]] || fail "API smoke test failed. Response: ${OUT:0:300}
Logs: aws logs tail $LOG_GROUP --region $REGION --since 10m"
echo "API OK: $API_URL"

# Prove the seat-booking transaction works with the deployed IAM role and table: book a seat, then cancel it.
LIB=$(curl -sS --max-time 25 "$API_URL/library?student_id=deploy-smoke" 2>&1) || LIB=""
SLOT=$(grep -o '"chosen": [0-9]*' <<< "$LIB" | grep -o '[0-9]*$' | head -1 || true)
SEAT=$(grep -o '"id": "[a-z]*-[A-Z][0-9]*", "status": "free"' <<< "$LIB" | head -1 | cut -d'"' -f4 || true)
[[ -n "$SLOT" && -n "$SEAT" ]] || fail "Library smoke test: could not read the seat map. Response: ${LIB:0:300}
Logs: aws logs tail $LOG_GROUP --region $REGION --since 10m"
BOOK=$(curl -sS --max-time 25 -X POST "$API_URL/library/book" -H 'Content-Type: application/json' \
  -d "{\"student_id\":\"deploy-smoke\",\"slot\":$SLOT,\"seat\":\"$SEAT\"}" 2>&1 || true)
[[ "$BOOK" == *'"seat"'* ]] || fail "Library smoke test: booking a seat failed (DynamoDB transaction or IAM permission?). Response: ${BOOK:0:300}
Logs: aws logs tail $LOG_GROUP --region $REGION --since 10m"
curl -sS --max-time 25 -X POST "$API_URL/library/cancel" -H 'Content-Type: application/json' \
  -d "{\"student_id\":\"deploy-smoke\",\"slot\":$SLOT}" > /dev/null || warn "Could not cancel the smoke-test seat (it expires on its own)."
echo "Library booking OK (seat $SEAT booked and cancelled)"

say "3/5 Preparing the frontend with your API address"
rm -rf .build && mkdir -p .build && cp -R frontend .build/frontend
printf 'window.CAMPUSPILOT_API = "%s";\n' "$API_URL" > .build/frontend/config.js
(cd .build/frontend && zip -qr ../frontend.zip . -x '.DS_Store')

say "4/5 Deploying the frontend (Amplify Hosting)"
APP_ID=$(aws amplify list-apps --region "$REGION" --query "apps[?name=='$STACK'].appId | [0]" --output text) \
  || fail "Could not list Amplify apps. Is Amplify available in $REGION, and does your IAM user allow amplify:*?"
if [[ -z "$APP_ID" || "$APP_ID" == "None" ]]; then
  APP_ID=$(aws amplify create-app --name "$STACK" --region "$REGION" --query app.appId --output text)
  aws amplify create-branch --app-id "$APP_ID" --branch-name main --region "$REGION" > /dev/null
fi
CSP="default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self' ${API_URL}; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
HEADERS=$'customHeaders:\n  - pattern: "**"\n    headers:\n      - key: X-Content-Type-Options\n        value: nosniff\n      - key: X-Frame-Options\n        value: DENY\n      - key: Referrer-Policy\n        value: no-referrer\n      - key: Permissions-Policy\n        value: "camera=(), microphone=(), geolocation=()"\n      - key: Strict-Transport-Security\n        value: "max-age=31536000; includeSubDomains"\n      - key: Content-Security-Policy\n        value: "'"${CSP}"'"'
aws amplify update-app --app-id "$APP_ID" --region "$REGION" --custom-headers "$HEADERS" > /dev/null \
  || warn "Could not apply security headers; the site will still work."
DEPLOY=$(aws amplify create-deployment --app-id "$APP_ID" --branch-name main --region "$REGION" \
  --query '[jobId,zipUploadUrl]' --output text)
read -r JOB_ID UPLOAD_URL <<< "$DEPLOY"
curl -sS --fail --max-time 120 -T .build/frontend.zip "$UPLOAD_URL" > /dev/null \
  || fail "Uploading the frontend zip failed. Check your network and run the script again."
aws amplify start-deployment --app-id "$APP_ID" --branch-name main --job-id "$JOB_ID" --region "$REGION" > /dev/null

STATUS=""
for _ in $(seq 1 40); do
  STATUS=$(aws amplify get-job --app-id "$APP_ID" --branch-name main --job-id "$JOB_ID" --region "$REGION" \
    --query job.summary.status --output text)
  case "$STATUS" in
    SUCCEED) break ;;
    FAILED | CANCELLED) fail "Amplify deployment $STATUS. Open the Amplify console, app '$STACK', branch 'main' for details." ;;
  esac
  sleep 3
done
[[ "$STATUS" == "SUCCEED" ]] || fail "Amplify deployment is still '$STATUS' after 2 minutes. Check the Amplify console."

say "5/5 Checking the live site"
URL="https://main.${APP_ID}.amplifyapp.com"
UP=""
for _ in $(seq 1 10); do
  curl -sSf --max-time 10 -o /dev/null "$URL/" 2> /dev/null && { UP=1; break; }
  sleep 3
done
[[ -n "$UP" ]] || warn "$URL is not responding yet. A new site can take a few minutes; try it in a browser shortly."
rm -rf .build

printf '\nDone.\n  App:  %s\n  API:  %s\n\nNext: open the app on your phone and on a laptop, then follow docs/TESTING.md.\n' "$URL" "$API_URL"
