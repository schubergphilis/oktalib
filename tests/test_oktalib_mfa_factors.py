from betamax import Betamax


def test_get_mfa_enrolled_factors(okta_client):
    with Betamax(okta_client.session).use_cassette('get_mfa_enrolled_factors'):
        user = okta_client.get_user_by_login('yhoorneman@dev.schubergphilis.com')
        factors = list(user.enrolled_factors())
        assert factors is not None
        assert len(factors) > 0
        assert factors[0].factor_type == 'signed_nonce'
        assert factors[0].provider == 'OKTA'
        assert factors[0].vendor_name == 'OKTA'
        assert factors[0].status == 'ACTIVE'
        assert factors[0].profile is not None


def test_supported_factors(okta_client):
    with Betamax(okta_client.session).use_cassette('supported_factors'):
        user = okta_client.get_user_by_login('yhoorneman@dev.schubergphilis.com')
        supported_factors = list(user.supported_factors())
        assert supported_factors is not None
        assert len(supported_factors) > 0
        assert supported_factors[0].factor_type == 'token:software:totp'
        assert supported_factors[0].provider == 'GOOGLE'
        assert supported_factors[0].vendor_name == 'GOOGLE'
        assert (
            supported_factors[0].enroll_link
            == f'{okta_client.host}/api/v1/users/{user.id}/factors'
        )


# TODO: add tests for
#   user mfa factors
#       get, list, delete factor
