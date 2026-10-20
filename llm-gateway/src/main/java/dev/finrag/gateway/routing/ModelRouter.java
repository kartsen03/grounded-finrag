package dev.finrag.gateway.routing;

import org.springframework.stereotype.Component;

import dev.finrag.gateway.config.GatewayProperties;
import dev.finrag.gateway.config.GatewayProperties.ModelKind;
import dev.finrag.gateway.provider.ModelProvider;
import dev.finrag.gateway.provider.ProviderRegistry;

/** Resolves a public model alias to the provider adapter and upstream model name that serve it. */
@Component
public class ModelRouter {

    private final GatewayProperties properties;
    private final ProviderRegistry registry;

    public ModelRouter(GatewayProperties properties, ProviderRegistry registry) {
        this.properties = properties;
        this.registry = registry;
    }

    public Route route(String alias, ModelKind kind) {
        GatewayProperties.Model model = properties.models().get(alias);
        if (model == null) {
            throw new RoutingException(RoutingException.Reason.UNKNOWN_MODEL, "unknown model '" + alias + "'");
        }
        if (model.kind() != kind) {
            throw new RoutingException(RoutingException.Reason.WRONG_KIND,
                    "model '" + alias + "' is a " + model.kind().name().toLowerCase() + " model");
        }
        ModelProvider provider = registry.get(model.provider()).orElseThrow(() -> new RoutingException(
                RoutingException.Reason.PROVIDER_DISABLED, "provider for model '" + alias + "' is not enabled"));
        return new Route(alias, provider, model.upstream());
    }

    public record Route(String alias, ModelProvider provider, String upstreamModel) {
    }
}
