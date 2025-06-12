# Extensions

## Abstract

Extensions are a means of extending the Agent2Agent (A2A) protocol with new data, requirements, methods, and state machines. Agents declare their support for extensions in their AgentCard, and clients can then opt-in to the behavior offered by the extension as part of requests they make to the agent. Extensions are identified by a URI and defined by their extension specification. Anyone is able to define, publish, and implement an extension.

## Introduction

The core A2A protocol is a solid basis for enabling communication between agents. However, it's clear that some domains require additional structure than what is offered by the generic methods in the protocol. Extensions were added to the protocol to help support these cases: with extensions, agents and clients can negotiate additional, custom logic to be layered on top of the core protocol.

### Scope of Extensions

The exact set of possible ways to use extensions is intentionally not defined. This is to facilitate the ability to use extensions to expand A2A beyond currently known use cases. However, some use cases are clearly forseeable, such as:

- Exposing new information in the AgentCard. An extension may not impact the request/response flow at all -- it can be simply used as a way to convey additional structured information to clients via the AgentCard. We refer to these as *data-only extensions*.
- Overlaying additional structure and state change requirements on the core request/response messages. An extension could, for example, require that all messages use DataParts that adhere to a specific schema. This type of extension effectively acts as a profile on the core A2A protocol, narrowing the space of allowed values. We refer to these as *profile extensions*.
- Adding new RPC methods entirely. Extensions may define that the agent implements more than the core set of protocol methods. We refer to these as *method extensions*.

There are some changes to the protocol that extensions *do not* allow. These are:

- Changing the definition of core data structures. Adding new fields or removing required fields to protocol-defined data structures is not supported. Extensions are expected to place custom attributes in the `metadata` map that is present on core data structures.
- Adding new values to enum types. Instead, extensions should use existing enum values and annotate additional semantic meaning in the `metadata` field.

These limitations exist to prevent extensions from breaking core type validations that clients and agents perform.

### Architecture Overview

[TODO: Diagram]
- Extensions are defined by a specification document
- The specification document defines the identifiers for the extension
- The AgentCard declares support for an extension by referencing the identifier and providing any configuration
- An implementation is built according to the specification
- A client has support for various extensions
- The client indicates extensions to activate in its request to the agent
- Extensions can change the content of data that passes over the protocol

## Extension Declaration

Agents declare their support for extensions in their `AgentCard` by including `AgentExtension` objects in their `AgentCapabilities` object.

- `uri`: The URI of the extension. This is an arbitrary identifier that the extension specification defines. Implementations of an extension use this URI to identify when to activate, and clients use this to determine extension compatibility.
- `required`: Whether the agent requires clients to use this extension.
- `description`: A description of how the agent uses the declared extension. Full details of a extension are intended to be in an extension specification. This field is useful to explain the connection between the agent and the extension.
- `params`: Extension-specific configuration. The expected values to be placed in this field, if any, are defined by the extension specification. This field can be used for specifying parameters of the extension or declaring additional agent-specific data.

### Required Extensions

While extensions are a means of enabling additional functionality, we anticipate that some agents will have stricter requirements than those expressible by the core A2A protocol. For example, an agent may require that all incoming messages are cryptographically signed by their author. Extensions that are declared `required` are intended to support this use case.

When an AgentCard declares a required extension, this is a signal to clients that some aspect of the extension impacts how requests are structured. Agents should not mark data-only extensions as required, since there is no direct impact on how requests are made to the agent.

If an AgentCard declares a required extension, and the client does not request activation of that required extension, Agents should return reject the incoming request and return an appropriate error code.

If a client requests extension activation, but does not follow an extension-defined protocol, the Agent should reject the request and return an appropriate validation failure message.

## Extension Specification

The details of an extension are defined by a specification. The exact format of this document is not specified, however it should contain at least:

- The specific URI(s) that extension implementations should identify and respond to. Multiple URIs may identify the same extension to account for versioning or changes in location of the specification document. Extension authors are encouraged to use a permanent identifier service, such as [w3id](https://w3id.org), to avoid a proliferation of URLs.

- The schema and meaning of objects specified in the `params` field of the `AgentExtension` object exposed in the `AgentCard`.

- The schemas of any additional data structures communicated between client and agent.

- Details of request/response flows, additional endpoints, or any other logic required to implement the extension.

### Extension Dependencies

Extensions may depend on other extensions. This dependency may be required, where the core functionality of the extension is unable to run without the presence of the dependent, or optional, where some additional functionality is enabled when another extension is present. Extension specifications should document the dependency and its type.

Extensions do not need to declare their dependencies in the `AgentExtension` object. Dependencies are inherently implicit: if a dependency is required, any correct implementation of that extension would therefore require the dependent extension to exist.

## Extension Activation

Extensions should default to being inactive. This provides a "default to baseline" experience, where extension-unaware clients are not burdened by the details and data provided by an extension. Instead, clients and agents perform negotiation to determine which extensions are active for a request. This negotiation is initiated by the client including an `X-A2A-Extensions` header in the HTTP request to the agent. The value of this header should be a list of extension URIs that the client is intending to activate.

Clients may request activation of any extension. Agents are responsible for identifying supported extensions in the request and performing the activation. Any requested extensions that are not supported by the agent can be ignored.

Not all extensions are activatable: data-only extensions exist solely to provide additional information via an AgentCard. Clients may still request activation of these extensions. Since the extension does not perform any additional logic upon activation, this should have no impact on the request.

If a client requests activation of an extension with a required dependency, that client must also request activation of, and adhere to requirements of, that dependent extension. If the client does not request all required dependencies for a requested extension, the server may fail the request with an appropriate error.

Once the agent has identified all activated extensions, the response should include an `X-A2A-Extensions` header identifying all extensions that were activated.

## Implementation Considerations

TODO

- Idea is to publish a package that contains the implementation logic for your extension

- Insertion into your A2A server/client should be as simple as, e.g., `.use(MyExtension)`
