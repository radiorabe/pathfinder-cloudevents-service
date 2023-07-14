# Pathfinder CloudEvents Microservice

Receives RestApi requests from [Pathfinder](https://www.telosalliance.com/distributed-decentralized-routing/routing-monitoring/axia-pathfinder-core-pro-broadcast-controller), converts them into [RaBe CloudEvents](https://radiorabe.github.io/events-spec/),
and stores the resulting CloudEvent in a [Kafka](https://kafka.apache.org/) topic.

This service aims at replacing the previous [LWRP based implementation](https://github.com/radiorabe/virtual-saemubox)
which itself was highly influenced by the original serial implementation that was carried over to the digital domain
during our analog to digital migration in an effort to reduce the migrations blast radius.

## Usage

The service is deployed to our container infrastructure and it provides a `/webhook` endpoint that receives POST
requests from Pathfinder. The body of this request contains information in a query string style, specifically
Pathfinder sends us a `event` and `channel` value. The `event` is either `OnAir` or `OffAir` and the channel
indicates which audio source is currently routed to our broadcast infrastructure.

Information on available configuration options is available via the `--help` argument:

```bash
podman run --rm ghcr.io/radiorabe/pathfinderevents pathfinderevents --help
```

## Links

* [Pathfinder RestApi documentation](https://docs.telosalliance.com/pathfinder-core-pro/pathfindercore-pro/devices#restapi)

## Release Management

The CI/CD setup uses semantic commit messages following the [conventional commits standard](https://www.conventionalcommits.org/en/v1.0.0/).
The workflow is based on the [RaBe shared actions](https://radiorabe.github.io/actions/)
and uses [go-semantic-commit](https://go-semantic-release.xyz/)
to create new releases.

The commit message should be structured as follows:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

The commit contains the following structural elements, to communicate intent to the consumers of your library:

1. **fix:** a commit of the type `fix` patches gets released with a PATCH version bump
1. **feat:** a commit of the type `feat` gets released as a MINOR version bump
1. **BREAKING CHANGE:** a commit that has a footer `BREAKING CHANGE:` gets released as a MAJOR version bump
1. types other than `fix:` and `feat:` are allowed and don't trigger a release

If a commit does not contain a conventional commit style message you can fix
it during the squash and merge operation on the PR.

## Build Process

The CI/CD setup uses [Docker build-push Action](https://github.com/docker/build-push-action)
 to publish container images. The workflow is based on the [RaBe shared actions](https://radiorabe.github.io/actions/).

## License

This application is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, version 3 of the License.

## Copyright

Copyright (c) 2023 [Radio Bern RaBe](http://www.rabe.ch)
