#!/usr/bin/env bash
# Deletes everything deploy.sh created (Amplify app + CloudFormation stack incl. DynamoDB data and logs).
#   ./scripts/destroy.sh        asks you to type the stack name to confirm
#   ./scripts/destroy.sh -y     no prompt
set -Eeuo pipefail
REGION="${AWS_REGION:-ap-south-1}"
STACK="${STACK_NAME:-campuspilot}"

fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
trap 'fail "A command failed on line $LINENO: $BASH_COMMAND"' ERR
command -v aws > /dev/null || fail "'aws' CLI is not installed."
aws sts get-caller-identity > /dev/null 2>&1 || fail "AWS credentials are missing or expired. Run 'aws configure' or 'aws sso login'."

if [[ "${1:-}" != "-y" ]]; then
  read -r -p "This permanently deletes stack '$STACK' and the Amplify app in $REGION. Type '$STACK' to confirm: " ANSWER
  [[ "$ANSWER" == "$STACK" ]] || { echo "Cancelled. Nothing was deleted."; exit 1; }
fi

APP_ID=$(aws amplify list-apps --region "$REGION" --query "apps[?name=='$STACK'].appId | [0]" --output text)
if [[ -n "$APP_ID" && "$APP_ID" != "None" ]]; then
  aws amplify delete-app --app-id "$APP_ID" --region "$REGION" > /dev/null
  echo "Deleted Amplify app $APP_ID"
else
  echo "No Amplify app named '$STACK' found (already deleted?)."
fi

if aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" > /dev/null 2>&1; then
  aws cloudformation delete-stack --stack-name "$STACK" --region "$REGION"
  echo "Deleting stack '$STACK'... (this can take a minute)"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK" --region "$REGION" \
    || fail "Stack deletion did not finish. Check the CloudFormation console for the blocking resource."
  echo "Deleted stack '$STACK'"
else
  echo "No stack named '$STACK' found in $REGION (already deleted?)."
fi
echo "Done. SAM also keeps a small shared S3 bucket for deployment artifacts (stack 'aws-sam-cli-managed-default'); delete that stack too if you won't deploy again."
