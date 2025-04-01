# Create App Runner Service Role
aws iam create-role --role-name CustomAppRunnerServiceRole `
    --assume-role-policy-document file://service-role-policy.json `
    --profile ansari --region us-west-2

aws iam attach-role-policy `
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess `
    --role-name CustomAppRunnerServiceRole `
    --profile ansari --region us-west-2

# Create GitHub Actions User
aws iam create-policy `
    --policy-name CustomGitHubActionsPolicy `
    --policy-document file://github-actions-policy.json `
    --profile ansari --region us-west-2

aws iam create-user `
    --user-name app-runner-github-actions-user `
    --profile ansari --region us-west-2

aws iam attach-user-policy `
    --policy-arn arn:aws:iam::<aws_account_id>:policy/CustomGitHubActionsPolicy `
    --user-name app-runner-github-actions-user `
    --profile ansari --region us-west-2

# Create an ECR Registry
aws ecr create-repository --repository-name ansari-backend `
    --profile ansari --region us-west-2

# Create App Runner Instance Role
aws iam create-role --role-name CustomAppRunnerInstanceRole `
    --assume-role-policy-document file://instance-role-policy.json `
    --profile ansari --region us-west-2

aws iam put-role-policy `
    --role-name CustomAppRunnerInstanceRole `
    --policy-name CustomAccessParameters `
    --policy-document file://instance-role-parameters-access.json `
    --profile ansari --region us-west-2

# Create staging env variables
aws ssm put-parameter `
  --name "/app-runtime/ansari-backend/staging/env-var-name" `
  --value "changethis" `
  --type SecureString `
  --profile ansari --region us-west-2

# Create production env variables
aws ssm put-parameter `
  --name "/app-runtime/ansari-backend/production/env-var-name" `
  --value "changethis" `
  --type SecureString `
  --profile ansari --region us-west-2