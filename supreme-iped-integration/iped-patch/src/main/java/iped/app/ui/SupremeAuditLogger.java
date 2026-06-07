package iped.app.ui;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * SupremeAuditLogger — Patch minimo para o iped-app.
 *
 * Usa reflection para acessar Document.get() sem importar Lucene,
 * permitindo compilacao sem nenhuma dependencia externa.
 * Em runtime o IPED ja carrega Lucene no classloader.
 *
 * Instalacao:
 *   1. Compilar: javac -d out SupremeAuditLogger.java  (sem CP especial)
 *   2. Empacotar: jar cf supreme-audit-patch.jar -C out .
 *   3. Copiar para IPED\plugins\supreme-audit-patch.jar
 *   4. Adicionar duas chamadas em ResultTableListener.processSelectedFile():
 *        SupremeAuditLogger.onItemClose(previousDocId, previousDoc);
 *        SupremeAuditLogger.onItemOpen(newDocId, newDoc);
 *   5. Definir SUPREME_AUDIT_LOG e SUPREME_USER_ID antes de lancar o IPED.
 */
public final class SupremeAuditLogger {

    private static final String LOG_PATH = System.getenv()
            .getOrDefault("SUPREME_AUDIT_LOG",
                    System.getProperty("user.home") + "/supreme_audit.ndjson");

    private static final String USER_ID = System.getenv()
            .getOrDefault("SUPREME_USER_ID", "unknown");

    private static final AtomicInteger lastDocId  = new AtomicInteger(-1);
    private static final AtomicLong    lastOpenMs = new AtomicLong(0);

    private static volatile BufferedWriter writer;
    private static volatile boolean        initialized = false;

    private static synchronized void ensureInit() {
        if (initialized) return;
        try {
            Path logPath = Paths.get(LOG_PATH);
            if (logPath.getParent() != null) {
                Files.createDirectories(logPath.getParent());
            }
            writer = Files.newBufferedWriter(logPath,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
            initialized = true;
            Runtime.getRuntime().addShutdownHook(new Thread(SupremeAuditLogger::flush));
        } catch (IOException e) {
            System.err.println("[SupremeAuditLogger] Falha ao abrir log: " + e.getMessage());
        }
    }

    // doc e um org.apache.lucene.document.Document — acessado via reflection
    public static void onItemOpen(int docId, Object doc) {
        if (docId < 0 || doc == null) return;
        ensureInit();
        lastDocId.set(docId);
        lastOpenMs.set(System.currentTimeMillis());
        writeEvent("open", docId, doc, lastOpenMs.get(), -1);
    }

    public static void onItemClose(int docId, Object doc) {
        if (docId < 0 || doc == null) return;
        ensureInit();
        long closeMs = System.currentTimeMillis();
        writeEvent("close", docId, doc, lastOpenMs.get(), closeMs);
    }

    public static void onBookmark(int docId, Object doc, String bookmark) {
        if (docId < 0 || doc == null) return;
        ensureInit();
        long now = System.currentTimeMillis();
        writeLine(buildJson("classification_event", docId, doc, now, now, bookmark));
    }

    private static void writeEvent(String event, int docId, Object doc,
                                   long openMs, long closeMs) {
        writeLine(buildJson(event, docId, doc, openMs, closeMs, null));
    }

    private static String buildJson(String event, int docId, Object doc,
                                    long openMs, long closeMs, String bookmark) {
        StringBuilder sb = new StringBuilder(256);
        sb.append("{");
        appendField(sb, "event",         event);
        appendField(sb, "itemId",        String.valueOf(docId));
        appendField(sb, "name",          safeGet(doc, "name"));
        appendField(sb, "path",          safeGet(doc, "path"));
        appendField(sb, "mediaType",     safeGet(doc, "contentType"));
        appendField(sb, "category",      safeGet(doc, "category"));
        appendField(sb, "nudityClass",   safeGet(doc, "nudityClass"));
        appendField(sb, "aiCsam",        safeGet(doc, "ai:csam"));
        appendField(sb, "aiPorn",        safeGet(doc, "ai:porn"));
        appendField(sb, "fileDurationMs",safeGet(doc, "duration"));
        appendField(sb, "openTs",        String.valueOf(openMs));
        appendField(sb, "closeTs",       String.valueOf(closeMs));
        appendField(sb, "userId",        USER_ID);
        if (bookmark != null) appendField(sb, "bookmark", bookmark);
        if (sb.length() > 1 && sb.charAt(sb.length() - 1) == ',')
            sb.setLength(sb.length() - 1);
        sb.append("}");
        return sb.toString();
    }

    private static void appendField(StringBuilder sb, String key, String value) {
        if (value == null || value.isEmpty()) return;
        sb.append("\"").append(key).append("\":\"")
          .append(value.replace("\\", "\\\\")
                       .replace("\"", "\\\"")
                       .replace("\n", "\\n"))
          .append("\",");
    }

    // Usa reflection: evita import de org.apache.lucene.document.Document
    private static String safeGet(Object doc, String field) {
        if (doc == null || field == null) return null;
        try {
            java.lang.reflect.Method m = doc.getClass().getMethod("get", String.class);
            Object result = m.invoke(doc, field);
            return result != null ? result.toString() : null;
        } catch (Exception e) {
            return null;
        }
    }

    private static synchronized void writeLine(String line) {
        if (writer == null) return;
        try {
            writer.write(line);
            writer.newLine();
            writer.flush();
        } catch (IOException e) {
            System.err.println("[SupremeAuditLogger] Erro ao escrever: " + e.getMessage());
        }
    }

    private static synchronized void flush() {
        try { if (writer != null) writer.close(); } catch (IOException ignored) {}
    }

    private SupremeAuditLogger() {}
}
