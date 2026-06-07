# SUPREME V4 — Build e Deploy do Patch IPED

## Visão geral

```
supreme-iped-integration/iped-patch/
├── pom.xml                              ← build do SupremeAuditLogger
├── src/main/java/iped/app/ui/
│   └── SupremeAuditLogger.java          ← classe que grava o log NDJSON
├── ResultTableListener.patch            ← instruções de modificação manual
└── BUILD.md                             ← este arquivo
```

O patch consiste em:
1. Compilar `SupremeAuditLogger.java` e incluir no classpath do IPED
2. Editar manualmente `ResultTableListener.java` no repositório IPED (open/close)
3. Editar manualmente `ResultTableModel.java` no repositório IPED (bookmarks)
4. Reconstruir o IPED com Maven

> **Compatibilidade verificada**: IPED master (4.4.0-SNAPSHOT). Em versões anteriores
> ao 4.4, o passo 3 pode ser aplicado em `BookmarksController.java` se esse arquivo
> tiver o método `setChecked()` diretamente.

---

## Pré-requisitos

| Ferramenta | Versão | Download |
|---|---|---|
| JDK Liberica Full (com JavaFX) | 11 ou 17 | https://bell-sw.com/pages/downloads/#jdk-11-lts |
| Maven | 3.8+ | https://maven.apache.org/download.cgi |
| Git | qualquer | https://git-scm.com |

> **Atenção**: use o **Liberica Full JDK 11** — o JDK padrão da Oracle não inclui JavaFX, que o IPED requer para compilar.

---

## Passo 1 — Clonar e buildar o IPED

```powershell
# Clonar o IPED (use a tag de produção desejada)
git clone https://github.com/sepinf-inc/IPED.git iped-source
cd iped-source
git checkout master   # ou a tag de produção desejada (ex: v4.2.2, v4.3.x)

# Build completo do IPED (necessário para instalar os artefatos no .m2)
mvn clean install -DskipTests -T4
```

Isso instala `iped-app`, `iped-engine`, `iped-api` no repositório Maven local (`~/.m2`), necessário para compilar o SupremeAuditLogger.

---

## Passo 2 — Aplicar a modificação em ResultTableListener.java

Edite manualmente o arquivo:
```
iped-source/iped-app/src/main/java/iped/app/ui/ResultTableListener.java
```

Localize o método `processSelectedFile` e o bloco:
```java
if (docId != lastAppDoc && (!isMouseEvent || docId == lastTableDoc)) {
    lastTableDoc = docId;
```

**Insira ANTES de `lastTableDoc = docId;`:**
```java
// ── SUPREME AUDIT PATCH ──────────────────────────────────────
int _supremePrev = lastTableDoc;
try {
    if (_supremePrev >= 0) {
        org.apache.lucene.document.Document _prevDoc =
            App.get().appCase.getSearcher().doc(_supremePrev);
        iped.app.ui.SupremeAuditLogger.onItemClose(_supremePrev, _prevDoc);
    }
    org.apache.lucene.document.Document _newDoc =
        App.get().appCase.getSearcher().doc(docId);
    iped.app.ui.SupremeAuditLogger.onItemOpen(docId, _newDoc);
} catch (Exception _supremeEx) {
    // nunca deixar auditoria quebrar a UI principal
}
// ── FIM SUPREME AUDIT PATCH ───────────────────────────────────
```

> **API correta**: `App.get().appCase.getSearcher().doc(docId)`
> Retorna `IndexSearcher` (Lucene) com `doc(int)` nativo. Já usado internamente
> pelo próprio `ResultTableListener.java` (linha 337) — API estável em todas as versões.
> **Não use**: `App.get().appCase.getReader().document(docId)` — pode falhar em índices multisource

---

## Passo 2b — Aplicar o patch de bookmarks em ResultTableModel.java

> **IPED 4.4+**: `BookmarksController.java` não tem `setChecked()`. O ponto correto é
> `ResultTableModel.java`.

Edite o arquivo:
```
iped-source/iped-app/src/main/java/iped/app/ui/ResultTableModel.java
```

Localize o método `setValueAt` e o bloco:
```java
public void setValueAt(Object value, int row, int col) {
    app.appCase.getMultiBookmarks().setChecked((Boolean) value, App.get().ipedResult.getItem(row));
```

**Insira ANTES de `app.appCase.getMultiBookmarks().setChecked(...)`:**
```java
// ── SUPREME CLASSIFICATION PATCH ─────────────────────────────
if (col == 1 && Boolean.TRUE.equals(value)) {
    try {
        iped.data.IItemId _bkItem = App.get().ipedResult.getItem(row);
        int _bkDocId = App.get().appCase.getLuceneId(_bkItem);
        org.apache.lucene.document.Document _bkDoc =
            App.get().appCase.getSearcher().doc(_bkDocId);
        iped.app.ui.SupremeAuditLogger.onBookmark(_bkDocId, _bkDoc, "bookmark");
    } catch (Exception _supremeEx) {}
}
// ── FIM SUPREME CLASSIFICATION PATCH ─────────────────────────
```

> `col == 1` é a coluna do checkbox de bookmark na tabela de resultados do IPED.
> O bloco só dispara quando o perito **marca** um item (value == true).

---

## Passo 3 — Copiar SupremeAuditLogger.java para o IPED

```powershell
# A partir da raiz do projeto SUPREME
copy supreme-iped-integration\iped-patch\src\main\java\iped\app\ui\SupremeAuditLogger.java `
     iped-source\iped-app\src\main\java\iped\app\ui\SupremeAuditLogger.java
```

---

## Passo 4 — Reconstruir o iped-app

```powershell
cd iped-source\iped-app
mvn clean package -DskipTests
```

O JAR atualizado fica em:
```
iped-source/iped-app/target/iped-app-*.jar
```
(o nome inclui a versão — ex: `iped-app-4.4.0-SNAPSHOT.jar`)

---

## Passo 5 — Deploy nas máquinas dos peritos

### 5a. Substituir o JAR

```powershell
# Identificar o JAR original (ajuste o nome à versão instalada)
$ipedJar = Get-ChildItem "C:\IPED" -Filter "iped-app-*.jar" | Select-Object -First 1

# Backup do JAR original
copy $ipedJar.FullName "$($ipedJar.FullName).bak"

# Instalar o JAR patched (ajuste o nome à versão compilada)
copy iped-source\iped-app\target\iped-app-*.jar $ipedJar.FullName
```

### 5b. Configurar variáveis de