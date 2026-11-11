# finnish-inflection-core

The Finnish inflection logic behind
[finnish-drill](https://github.com/reedpen/finnish-inflection): analyzing word
lists, generating full inflection tables with UralicNLP, building question
pools, and progressive hints.

The library does no printing, file, network, or clock access of its own.
Callers pass in the morphology model, so it works the same in a terminal app,
a web server, or tests.

Licensed under the Apache License 2.0. The Finnish model that UralicNLP
downloads (Omorfi) is GPL-licensed and is not part of this package.
