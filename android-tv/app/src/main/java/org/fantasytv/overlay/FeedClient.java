package org.fantasytv.overlay;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import javax.net.ssl.HttpsURLConnection;

/** HTTPS only; no redirects, permissive certificates, disk cache or response logging. */
final class FeedClient {
    String fetch(String endpoint, String token) throws IOException {
        URI uri = EndpointPolicy.validate(endpoint);
        HttpsURLConnection connection = (HttpsURLConnection)uri.toURL().openConnection();
        connection.setConnectTimeout(4000); connection.setReadTimeout(4000);
        connection.setInstanceFollowRedirects(false); connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("Cache-Control", "no-cache");
        connection.setRequestProperty("Accept-Encoding", "identity");
        token = EndpointPolicy.token(token);
        if (!token.isEmpty()) connection.setRequestProperty("Authorization", "Bearer " + token);
        final long deadline = System.nanoTime() + 12_000_000_000L;
        try {
            if (connection.getResponseCode() != 200) throw new IOException("Feed request failed");
            String type = connection.getContentType();
            if (type == null || !type.toLowerCase(java.util.Locale.ROOT).startsWith("application/json")) throw new IOException("Invalid feed content type");
            if (connection.getContentLengthLong() > 1_048_576) throw new IOException("Feed is too large");
            try (InputStream stream = connection.getInputStream(); ByteArrayOutputStream body = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192]; int read;
                while ((read = stream.read(buffer)) != -1) {
                    if (System.nanoTime() > deadline) throw new IOException("Feed request timed out");
                    if (body.size() + read > 1_048_576) throw new IOException("Feed is too large");
                    body.write(buffer, 0, read);
                }
                return new String(body.toByteArray(), StandardCharsets.UTF_8);
            }
        } finally { connection.disconnect(); }
    }
}
