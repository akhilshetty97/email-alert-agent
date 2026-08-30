# Privacy Policy

**LinkedIn Park** is a personal, single-user application operated by its owner
for their own use only. It is not offered as a service to other people.

## What it does

The app reads the owner's own Gmail messages to detect job-search-related emails
(interviews, assessments, next steps) and sends the owner a notification via
Telegram. It also applies a label to processed messages in the owner's mailbox.

## Data access and use

- The app accesses the owner's Gmail via Google's official API using the
  `gmail.modify` scope, solely to read message content and add a label.
- Email content is sent to the OpenAI API only for the purpose of classifying
  whether a message is a relevant job-search email.
- The app does not sell, share, or transfer any data to third parties beyond the
  service providers listed above (Google, OpenAI, Telegram), which are used only
  to provide the app's core function.

## Data storage and retention

- The app does not operate a database. It stores no email content.
- Deduplication state is kept as a Gmail label within the owner's own mailbox.
- OAuth credentials are stored locally / in the owner's own deployment secrets.

## Contact

For any questions, contact the repository owner via the GitHub repository:
https://github.com/akhilshetty97/ai-agent-notify-email
