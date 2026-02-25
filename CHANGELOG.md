# Changelog

All notable changes to this project will be documented in this file.

## [3.1.0](https://github.com/schubergphilis/oktalib/compare/v3.0.0...v3.1.0) (2026-02-25)


### Features

* adding type hints for entities & addition of _missing_required_fields and _validate_fields in entity that is implemented for groups to satisfy the static checks. ([180fec0](https://github.com/schubergphilis/oktalib/commit/180fec06a5aada2204cb07c7274417ec2bc6d6ca))
* integrate paleofuturistic framework and improve CI/CD, typing, and docs ([7b0852c](https://github.com/schubergphilis/oktalib/commit/7b0852ca95cf569cb8ecb479045ecd53da8d7883))


### Bug Fixes

* avoids passing None or other non-text values into dateutil.parser.parse which mypy warns about ([ce6f426](https://github.com/schubergphilis/oktalib/commit/ce6f426284d44b476ab9603899b688d2b7fd8bbc))
* more type hints in core.py ([95ec701](https://github.com/schubergphilis/oktalib/commit/95ec7010ba5e959d78e4b0df80a209a140bcbd9f))
* mypy errors ([d6f5939](https://github.com/schubergphilis/oktalib/commit/d6f5939c9e14f26d12221511535f00f5fab991cb))
* the dynamic assignment on session is fine at run time but not for mypy since it doesn't adhere to the stub ([5756c96](https://github.com/schubergphilis/oktalib/commit/5756c967e277bd1d80adee43b6ba41a7d9c472d2))
* update _validate_fields method to use instance reference instead of class reference ([b084a6e](https://github.com/schubergphilis/oktalib/commit/b084a6e19ffa3bc2bd080313bbf267b4f1d2699b))

## [3.0.0] - 2026-02-12

* Migrated to Paleofuturistic Python template
* Updated to Python 3.12+ minimum requirement
* Migrated documentation from Sphinx to MkDocs with mkdocstrings
* Updated build system to use uv

## [2.1.0] - 2023-11-06

* Add admin role support
* Bump minimum python version to 3.9
* Clean up and update structure

## [2.0.2] - 2023-03-07

* Test release

## [2.0.1] - 2023-02-28

* Testing release

## [2.0.0] - 2023-01-30

* Fixed a nasty bug with activate and deactivate of applications being exposed as properties with bad side effects on introspection
* Made most entities return as generators

## [1.6.1] - 2022-04-22

* Fixed bugs with api rate limiting courtesy of Yorick Hoorneman <yhoorneman@schubergphilis.com>

## [1.6.0] - 2022-03-28

* Made entities comparable

## [1.5.0] - 2022-03-24

* Added User and Group assignment roles

## [1.4.5] - 2021-06-08

* Reverted pypi reference to legacy

## [1.4.4] - 2021-06-08

* Updated pypi reference

## [1.4.3] - 2021-06-08

* Updated reference of pypi to simple from legacy

## [1.4.2] - 2021-06-08

* Bumped dependencies

## [1.4.1] - 2021-04-26

* Bumped dependencies

## [1.4.0] - 2021-03-15

* Added property setters for user attributes

## [1.3.0] - 2020-12-02

* Bumped requests

## [1.2.0] - 2020-10-09

* Bumped requests

## [1.1.13] - 2020-06-17

* Fixed applications entity

## [1.1.12] - 2020-06-09

* Bumped requests

## [1.1.11] - 2020-01-13

* Corrected Pipfile.lock issue

## [1.1.10] - 2020-01-13

* Added api exhaustion backoff

## [1.1.9] - 2019-12-19

* Added feature for aws application

## [1.1.8] - 2019-10-18

* Updated template and bumped dependencies

## [1.1.7] - 2019-10-18

* Bumped dependencies

## [1.1.6] - 2019-09-23

* Fix applications method

## [1.1.5] - 2019-09-20

* Added limit

## [1.1.4] - 2019-09-20

* Update get_application_by_id

## [1.1.3] - 2019-01-11

* Updated requests module and fixed requirements generation

## [1.1.2] - 2018-12-17

* Updated requests version

## [1.1.1] - 2018-10-25

* Updated template and dependencies

## [1.1.0] - 2018-10-23

* Added setting of user password capability

## [1.0.0] - 2018-10-19

* Updated template to python3.7
* Dropped support for python2.7

## [0.1.0] - 2018-05-25

* First release
