package dev.finrag.gateway.routing;

import java.util.ArrayList;
import java.util.List;

import org.springframework.stereotype.Component;

import dev.finrag.gateway.config.GatewayProperties;
import dev.finrag.gateway.config.GatewayProperties.ModelKind;
import dev.finrag.gateway.provider.ProviderRegistry;

/**
 * Resolves a public model alias to an ordered list of routes: the primary provider, then the
 * configured fallbacks, skipping providers that are not enabled (e.g. a hosted provider with no
 * API key). The caller tries them in order.
 */
@Component
public class ModelRouter {

    private final GatewayProperties properties;
    private final ProviderRegistry registry;

    public ModelRouter(GatewayProperties properties, ProviderRegistry registry) {
        this.properties = properties;
        this.registry = registry;
    }

    public GatewayProperties.Model model(String alias, ModelKind kind) {
        GatewayProperties.Model model = properties.models().get(alias);
        if (model == null) {
            throw new RoutingException(RoutingException.Reason.UNKNOWN_MODEL, "unknown model '" + alias + "'");
        }
        if (model.kind() != kind) {
            throw new RoutingException(RoutingException.Reason.WRONG_KIND,
                    "model '" + alias + "' is a " + model.kind().name().toLowerCase() + " model");
        }
        return model;
    }

    public List<Route> routes(String alias, ModelKind kind) {
        GatewayProperties.Model model = model(alias, kind);
        List<GatewayProperties.Target> targets = new ArrayList<>();
        targets.add(new GatewayProperties.Target(model.provider(), model.upstream()));
        targets.addAll(model.fallbacks());
        List<Route> routes = new ArrayList<>();
        for (GatewayProperties.Target t : targets) {
            registry.get(t.provider()).ifPresent(p -> routes.add(new Route(alias, p, t.upstream())));
        }
        if (routes.isEmpty()) {
            throw new RoutingException(RoutingException.Reason.PROVIDER_DISABLED,
                    "no enabled provider for model '" + alias + "'");
        }
        return routes;
    }

    public record Route(String alias, dev.finrag.gateway.provider.ModelProvider provider, String upstreamModel) {
    }
}
