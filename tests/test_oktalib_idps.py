from betamax import Betamax


def test_get_idps(okta_client):
    with Betamax(okta_client.session).use_cassette('get_idps'):
        idps = list(okta_client.idps)
        assert idps is not None
        assert len(idps) > 0


def test_create_saml_idp(okta_client):
    with Betamax(okta_client.session).use_cassette('create_saml_idp'):
        idp = okta_client.create_saml_idp(
            name='yorick-oktalib-saml-idp-test',
            okta_idp_issuer_url='http://www.okta.com/exkhrf48i3A8IdCIW0i7',
            okta_idp_sso_url='https://schubergphilis.okta-emea.com/app/schubergphilis_yorickmfaclaimtestapp_1/exkhrf48i3A8IdCIW0i7/sso/saml',
            kid='292640fd-2710-4291-90cd-f42c4d7ab4d7',
            idp_username='idpuser.subjectNameId',
            trust_claims=True,
            users_regex_filter='.*@dev.schubergphilis.com',
            account_link_exclude_admins=True,
            account_link_group_filter=['00g2nlcj9fmokDqGl0h8'],
            account_link_exclude_users=['00uxpw72gdBD7nxfL0h7'],
        )
        assert idp is not None
        assert idp.name == 'yorick-oktalib-saml-idp-test'
        assert idp.type == 'SAML2'
        assert idp.claims
        assert (
            idp.policy.get('accountLink', {})
            .get('filter', {})
            .get('users', {})
            .get('excludeAdmins')
        )
        assert idp.policy.get('accountLink', {}).get('filter', {}).get(
            'groups', {}
        ).get('include') == ['00g2nlcj9fmokDqGl0h8']
        assert idp.policy.get('accountLink', {}).get('filter', {}).get('users', {}).get(
            'exclude'
        ) == ['00uxpw72gdBD7nxfL0h7']


def test_replace_saml_idp(okta_client):
    with Betamax(okta_client.session).use_cassette('replace_saml_idp'):
        idp = okta_client.create_saml_idp(
            name='yorick-oktalib-saml-idp-test',
            okta_idp_issuer_url='http://www.okta.com/exkhrf48i3A8IdCIW0i7',
            okta_idp_sso_url='https://schubergphilis.okta-emea.com/app/schubergphilis_yorickmfaclaimtestapp_1/exkhrf48i3A8IdCIW0i7/sso/saml',
            kid='292640fd-2710-4291-90cd-f42c4d7ab4d7',
            idp_username='idpuser.subjectNameId',
            trust_claims=True,
            users_regex_filter='.*@dev.schubergphilis.com',
            account_link_exclude_admins=True,
            account_link_group_filter=['00g2nlcj9fmokDqGl0h8'],
            account_link_exclude_users=['00uxpw72gdBD7nxfL0h7'],
        )
        idp.name = 'yorick-oktalib-saml-idp-test-REPLACED'
        idp = okta_client.get_idp_by_name('yorick-oktalib-saml-idp-test-REPLACED')
        assert idp is not None


# TODO:
#   disable, delete
