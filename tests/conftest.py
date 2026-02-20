import json
import os

import pytest
from betamax import Betamax
from betamax.cassette import Interaction

from oktalib import Okta


def sanitize_sensitive_data(interaction: Interaction, current_cassette):
    """Remove sensitive keys from JSON responses and requests."""
    # Sanitize request headers
    request = interaction.data['request']
    request_headers = request.get('headers', {})
    if 'authorization' in request_headers:
        request_headers['authorization'] = ['<REDACTED>']
    if 'Cookie' in request_headers:
        request_headers['Cookie'] = ['<REDACTED>']

    # Sanitize response
    response = interaction.data['response']
    response_headers = response.get('headers', {})

    # Remove authorization header from response if present (shouldn't be there normally)
    if 'authorization' in response_headers:
        response_headers['authorization'] = ['<REDACTED>']

    # Sanitize response body if it's JSON
    if 'application/json' in response_headers.get('content-type', [''])[0]:
        try:
            body = json.loads(response['body']['string'])
            # Replace sensitive keys
            if 'apiKey' in body:
                body['apiKey'] = '<REDACTED>'
            if 'credentials' in body:
                body['credentials'] = '<REDACTED>'
            response['body']['string'] = json.dumps(body)
        except (json.JSONDecodeError, KeyError):
            pass


with Betamax.configure() as config:
    config.cassette_library_dir = 'tests/vcr/cassettes'
    config.before_record(callback=sanitize_sensitive_data)
    config.default_cassette_options['match_requests_on'] = [
        'method',
    ]
    # Define placeholder to mask the actual Okta host
    okta_host = os.environ.get('OKTA_HOST', 'https://example.com')
    config.define_cassette_placeholder('<OKTA_HOST>', okta_host)
    # Also define a bare hostname placeholder (without https://)
    okta_host_bare = okta_host.replace('https://', '').replace('http://', '')
    config.define_cassette_placeholder('<OKTA_HOST_BARE>', okta_host_bare)


### Okta ###


@pytest.fixture
def okta_client():
    """Mock Okta client."""
    host = os.environ.get('OKTA_HOST', 'https://example.com')
    token = os.environ.get('OKTA_API_KEY', 'fake_api_key')
    return Okta(host, token)
