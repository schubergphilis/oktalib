from betamax import Betamax


def test_get_idp_keys(okta_client):
    with Betamax(okta_client.session).use_cassette('get_idp_keys'):
        keys = list(okta_client.get_idp_keys())
        assert keys is not None
        assert len(keys) > 0
        assert keys[0].kid == '1bc1ad82-2818-4a29-9c1b-945dad3d18eb'
        assert keys[0].alg == 'RSA'


# TODO: add tests for
#   idpkeys
#      get_idp_key_by_kid
#      delete_idp_key
#      create idp_key providing x509 certificate
