# Gemini API Console App

For use with:
 - https://exchange.gemini.com/
 - https://exchange.sandbox.gemini.com/

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

Before trading live, you can get used to the app with the Gemini sandbox exchange by creating a test account here:
https://exchange.sandbox.gemini.com/

To set a default sandbox API `account-key` and `secret-key`, create a `./sandbox.yaml`:
```
# sandbox API test key for use with https://exchange.sandbox.gemini.com
api_key: "your-account-key"
secret_key: "your-secret-key"
```
