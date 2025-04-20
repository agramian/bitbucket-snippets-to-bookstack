# Bitbucket Snippets to Bookstack

A Python script to migrate Bitbucket snippets to Bookstack books and pages.

## Features
- Automatically creates books named using the snippet titles and pages for each file of a snippet named using the filenames.
- Supports skipping books and pages that already exist via arguments.
- Creates revisions for previous snippet changes.
- Snippet content will be placed into Bookstack pages as Markdown. 

## Limitations
- Previous revisions are created sequentially and timestamped to the moment of their creation because Bookstack does not support 
  backdating revisions.
- Accurately tracking file renames or deletions across Bitbucket commits via the API can be complex. This script will attempt to 
  get the content for a specific filename at each commit hash. If a file didn't exist (or was named differently) in an old commit, the content fetch will likely fail (e.g., 404 error), and the script will skip creating a revision for that file/page in Bookstack for that specific commit. This implicitly handles history reasonably well for files that persist.
- Bookstack pages usually use HTML or Markdown. Bitbucket snippets are plain text based on their file type. This script assumes 
  the snippet content can be placed directly into a Bookstack page's markdown field. You might need manual adjustments if complex 
  conversions are required. 

## Requirements
- Python 3.7+.

## Usage
1. [Create a Bitbucket App password](https://support.atlassian.com/bitbucket-cloud/docs/create-an-app-password/).
1. [Create a Bookstack API Token](https://demo.bookstackapp.com/api/docs#authentication).
1. Install the script dependencies either globally or in a virtual environment:

   **Option 1 (global)**

         pip install .

   **Option 2 (virtual environment)**

         python -m venv venv
         source venv/bin/activate
         python -m pip install .

1. Run the script

         python migrate_bitbucket_snippets_to_bookstack.py \
         --bb-user "your_bitbucket_username" \
         --bb-app-password "your_bitbucket_app_password" \
         --bs-url "https://your-bookstack-domain.com" \
         --bs-token-id "your_bookstack_token_id" \
         --bs-token-secret "your_bookstack_token_secret" \
         --bb-workspace "your_bitbucket_workspace_id" \
         # Optional: Add --skip-existing-books if you don't want to update books that already exist
         # Optional: Add --skip-existing-pages if you don't want to update pages that already exist
         # Optional: Add --test-snippet-id to test the script with a single snippet

*Note: some systems may require explicitly using `python3` to ensure Python 3 is used when installing the dependendencies and 
running the script.*

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
