.PHONY: install synth deploy destroy

install:
	pip install -r requirements.txt

synth:
	cdk synth

deploy:
	cdk deploy --all --require-approval never

destroy:
	cdk destroy --all --force
