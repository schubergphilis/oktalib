from betamax import Betamax


def test_get_application_metadata(okta_client):
    with Betamax(okta_client.session).use_cassette('application_metadata'):
        metadata = okta_client.get_application_metadata(
            id_='0oa8wjn4dqEcMiAkg416',
            kid='7at6cw_4I0mZp8zsfUHxauBecxPeBsOk9mIpLTXbvtQ',
        )
        sso = metadata.single_sign_on_services
        cert = metadata.x509_certificate

        assert metadata is not None
        assert metadata.entity_id == 'http://www.okta.com/exk8wjn4cMyWlXxIM416'
        assert sso is not None
        assert (
            sso.http_post
            == f'{okta_client.host}/app/some_sbpokta_1/exk8wjn4cMyWlXxIM416/sso/saml'
        )
        assert (
            cert is not None
            and 'MIIDljCCAn6gAwIBAgIGAXVqKdiXMA0GCSqGSIb3DQEBCwUAMIG' in cert
        )


# TODO: add tests for
#   application
#      get_application_by_sign_on_mode
#      create
