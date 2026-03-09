# Next Steps


## Extract metadata

- Consider Anthropic’s Sonnet 4
- Test on new metadata schemas
- Consider requesting a higher TPM rate

## Fix Metadata

- Consider additional data sources for the LLM stage
- Collect data on common errors made by uploaders to enable a personalized error correction experience and tailor correction stages based on real-world data

## Transform metadata

- Update file names/location logic for schemas and dictionary files to follow your file naming mechanism
- Add schema description for source tables for LLM in batch_semantic_column_match function to use
- Test a variety of data and tweak LLM prompts accordingly

