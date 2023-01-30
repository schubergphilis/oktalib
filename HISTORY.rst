.. :changelog:

History
-------

0.1.0 (25-05-2018)
------------------

* First release


1.0.0 (19-10-2018)
------------------

* Updated template to python3.7 Dropped support for python2.7


1.1.0 (23-10-2018)
------------------

* Added setting of user password capability


1.1.1 (25-10-2018)
------------------

* Updated template and dependencies


1.1.2 (17-12-2018)
------------------

* Updated requests version.


1.1.3 (11-01-2019)
------------------

* Updated requests module and fixed requirements generation.


1.1.4 (20-09-2019)
------------------

* Update get_applicatio_by_id


1.1.5 (20-09-2019)
------------------

* Added limit


1.1.6 (23-09-2019)
------------------

* Fix applications method


1.1.7 (18-10-2019)
------------------

* bumped dependencies


1.1.8 (18-10-2019)
------------------

* Updated template and bumped dependencies


1.1.9 (19-12-2019)
------------------

* Added feature for aws application


1.1.10 (13-01-2020)
-------------------

* Added api exhaustion backoff.


1.1.11 (13-01-2020)
-------------------

* Corrected Pipfile.lock issue.


1.1.12 (09-06-2020)
-------------------

* Bumped requests


1.1.13 (17-06-2020)
-------------------

* fixed applications entity


1.2.0 (09-10-2020)
------------------

* bumped requests


1.3.0 (02-12-2020)
------------------

* Bumped requests


1.4.0 (15-03-2021)
------------------

* Added property setters for user attributes.


1.4.1 (26-04-2021)
------------------

* Bumped dependencies.


1.4.2 (08-06-2021)
------------------

* Bumped dependencies.


1.4.3 (08-06-2021)
------------------

* Updated reference of pypi to simple from legacy.


1.4.4 (08-06-2021)
------------------

* Updated pypi reference.


1.4.5 (08-06-2021)
------------------

* Reverted pypi reference to legacy.


1.5.0 (24-03-2022)
------------------

* Added User and Group assignment roles.


1.6.0 (28-03-2022)
------------------

* Made entities comparable.


1.6.1 (22-04-2022)
------------------

* Fixed bugs with api rate limiting courtesy of Yorick Hoorneman <yhoorneman@schubergphilis.com>


2.0.0 (30-01-2023)
------------------

* Fixed a nasty bug with activate and deactivate of applications being exposed as properties with bad side effects on introspection. Made most entities return as generators.
