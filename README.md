# Gemini API Console App

For use with:
 - https://exchange.gemini.com/
 - https://exchange.sandbox.gemini.com/

## Quick Start
1. Create a test account on: https://exchange.sandbox.gemini.com/

2. [Create an API Key](https://exchange.sandbox.gemini.com/settings/api) with `Primary` scope and `Trading` permissions.

3. Install [Docker Desktop for Mac](https://hub.docker.com/editions/community/docker-ce-desktop-mac)

4. Run the app
```
docker run -it prasek/gemini
```

## Local
 To get started on OSX:

```
 brew install python
 pip3 install virtualenv
 make
```

To run after initial install:
```
make run
```

### Sandbox Exchange for Testing
Before trading live, you can get used to the app with the Gemini sandbox exchange by creating a test account here:
https://exchange.sandbox.gemini.com/

To set a default sandbox API `account-key` and `secret-key`, create a `./sandbox.yaml`:
```
# sandbox API test key for use with https://exchange.sandbox.gemini.com
api_key: "your-account-key"
secret_key: "your-secret-key"
```

### Live Exchange
Normally you'd manually enter your live exchange credentials each time you use the console app.

If you have a secure system you can setup default live credentials in `./live.yaml` which
must have a 600 file permission to be read by the app.

It's recommended to use an API token with restricted perimssions, e.g. Auditor.

To set a default live API `account-key` and `secret-key`, create a `./live.yaml`:
```
# live API test key for use with https://exchange.gemini.com
api_key: "your-account-key"
secret_key: "your-secret-key"
```

Then set the required 600 permission:
```
chmod 600 live.yaml
```

### Config Options
You can customize config options with the `set opt` command or in `./config.yaml`:
```
reserve_api_fees: none
debug: on
```
