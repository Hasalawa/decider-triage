# Setup notes for the workflows

## 1. Push the repo (required for the hackathon: public repo)

```bash
git remote add origin https://github.com/Hasalawa/decider-triage.git
git push -u origin main
```
`ci.yml` needs no secrets. Pushing to `main` starts it; check the Actions tab for a green tick.

## 2. `real-decider.yml` (optional, recommended before you write the article)

Actions tab -> "Real Decider benchmark" -> Run workflow. It downloads the model on a CPU runner,
so expect it to be slower than the 115 ms GPU figure in the Decider README. Quote the numbers it
prints along with the hardware ("GitHub-hosted CPU runner").

## 3. `release.yml` (optional, PyPI)

1. Rename the package in `pyproject.toml` if `decider-triage` is taken on PyPI.
2. pypi.org -> Publishing -> add a pending publisher: repo `Hasalawa/decider-triage`,
   workflow `release.yml`, environment `pypi`.
3. GitHub repo -> Settings -> Environments -> create `pypi`.
4. `git tag v0.1.0 && git push origin v0.1.0`.

Not needed for the hackathon. A public repo is enough.

## 4. `deploy-lambda.yml` (optional, be realistic)

The workflow only ships the *agent* code. The Decider is a 2B-parameter model server, which
does not fit a normal Lambda. Run `strands-decider serve` on an EC2 GPU/CPU instance or a
container service and point `DECIDER_URL` at it (keep it inside your VPC, it has no auth).

1. Create a Lambda (Python 3.12) with handler `lambda_handler.handler` and env `DECIDER_URL`.
2. Give its execution role `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`.
3. Create an IAM role trusting GitHub OIDC for your repo, allowed to `lambda:UpdateFunctionCode`.
4. Repo -> Settings -> Variables: `AWS_ROLE_ARN`, `AWS_REGION`, `LAMBDA_FUNCTION`.

Skip this for the submission unless you have time: the demo does not need it.
