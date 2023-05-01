# Orange PL Exporter

A prometheus exporter for Orange PL prepaid account balance.

Currently it only supports prepaid accounts and only the following details are exported:
- account balance
- account expiration date
- data allowances sum
- data allowances itemized + expiration date

## Usage

Configuration is loaded from a file called `accounts.json` in the current directory. The file should contain a JSON array of objects with the following keys: `username`, `password`

Example:
```json
[
  {
    "username": "123456789",
    "password": "password"
  }
]
```

Obtain metrics from the `/metrics` endpoint.