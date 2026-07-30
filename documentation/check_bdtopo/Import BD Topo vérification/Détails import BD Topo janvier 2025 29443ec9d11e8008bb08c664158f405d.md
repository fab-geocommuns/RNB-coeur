# Détails import BD Topo janvier 2025

## Import janvier 2025

![Extrait triés au hasard de 10 000 candidats inspectés lors de l’import de janvier 2025](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-04_a_09.13.55.png)

Extrait triés au hasard de 10 000 candidats inspectés lors de l’import de janvier 2025

**Vérifications visuelles**

- créations : 50
- verification “vrais updates” : tous

**Cas 1 : bâtiment de forme bizarre pour compléter la forme de bâtiments déjà connus**

Initialement, le RNB contient 3 bâtiments (XA34N811VNDM, 2CFDNCGPP1M3, RVG8PRHF4PD7) qui, je pense, sont censés représenter la maison dans son ensemble. La forme étant très mal calée sur la vue aérienne, la BD Topo vient compléter en créant un bout supplémentaire (bleu ci-dessous). On se retrouve avec un bâtiment en plus, qui n’améliore pas vraiment la précision du RNB.

![Etat du RNB avant inspection](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-03_a_16.52.08.png)

Etat du RNB avant inspection

![Etat après inspection : le bâtiment bleu a été créé](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-03_a_16.54.24.png)

Etat après inspection : le bâtiment bleu a été créé

On a un cas similaire ci-dessous : 

![Bâtiments à côté de KQKNP5T83NC3](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-03_a_17.15.18.png)

Bâtiments à côté de KQKNP5T83NC3

![Etat après inspection : le bâtiment bleu a été créé](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-03_a_17.16.14.png)

Etat après inspection : le bâtiment bleu a été créé

![TB9XE711M9EG](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-04_a_09.49.01.png)

TB9XE711M9EG

![Etat après inspection : le bâtiment bleu a été créé. On peut penser qu’il s’agit du même bâtiment que la maison à laquelle il est attaché. La BD Topo ne le considère pas comme un bâtiment léger.](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-04_a_09.50.23.png)

Etat après inspection : le bâtiment bleu a été créé. On peut penser qu’il s’agit du même bâtiment que la maison à laquelle il est attaché. La BD Topo ne le considère pas comme un bâtiment léger.

---

## Vérification des créations de bâtiments alors que la bâtiment BD Topo avait déjà un RNB ID attaché

**dpt 35**

```sql
checked 972085 features
found 12805 creation rows
found 5 problems
[('BATIMENT0000000297133046', 'Z2VS6E26QJE6'), ('BATIMENT0000000297168813', 'Y7FAR58JZWEP'), ('BATIMENT0000000297987007', 'AN2VBEMBEX75'), ('BATIMENT0000000298153526', 'Y6BHAF99JYBN'), ('BATIMENT0000000298165013', 'Q7P65ZNHBKZW')]
```

**BATIMENT0000000297133046**

![Batiment RNB existant (Z2VS6E26QJE6)](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-18_a_16.18.15.png)

Batiment RNB existant (Z2VS6E26QJE6)

![Bâtiment nouvellement créé mais contenant l’identifiant Z2VS6E26QJE6 dans la bd topo](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-18_a_16.19.33.png)

Bâtiment nouvellement créé mais contenant l’identifiant Z2VS6E26QJE6 dans la bd topo

Dans le cas où on permet la création : 

- 👎 On aurait deux bâtiments l’un à côté de l’autre là où il n’y en a qu’un seul
- 👎 Le lien bd topo ↔ rnb id serait à recalculer pour que le nouveau bâtiment RNB soit celui lié dans la BD Topo (besoin de refaire tout l’appariement BD Topo ↔ RNB à chaque fois ?)
- 👎 On a un nouveau bâtiment dont l’adresse est vide
- 👍 On a un nouveau bâtiment dont la forme correspond à la réalité

Dans le cas où on ne permet pas la création : 

- 👍 On a un seul bâtiment ce qui correspond à la réalité
- 👍 On conserve un lien valide BD Topo ↔ RNB
- 👎 On a un bâtiment dont

**BATIMENT0000000297168813**

![Bâtiment RNB, désactivé (Y7FAR58JZWEP)](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-18_a_16.26.59.png)

Bâtiment RNB, désactivé (Y7FAR58JZWEP)

![Bâtiment qui serait créé](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-18_a_16.47.33.png)

Bâtiment qui serait créé

La création est justifiée. Il semble que le bâtiment désactivé (car léger) ait été démoli et remplacé par le bâtiment bleu.

Si création : 

- 👍 On a un bâtiment qui correspond à la réalité
- 👎 Il faut recalculer le lien BD Topo ↔

**BATIMENT0000000297987007**

![Le bâtiment désactivé dans le RNB (AN2VBEMBEX75)](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-18_a_17.24.13.png)

Le bâtiment désactivé dans le RNB (AN2VBEMBEX75)

![Bâtiment qui serait créé (à juste titre) mais contenant le RNB ID du bâtiment rouge](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-18_a_17.24.01.png)

Bâtiment qui serait créé (à juste titre) mais contenant le RNB ID du bâtiment rouge

![Capture d’écran 2025-02-18 à 17.24.22.png](D%C3%A9tails%20import%20BD%20Topo%20janvier%202025/Capture_decran_2025-02-18_a_17.24.22.png)

**dpt 14**

```sql
checked 694985 features
found 8228 creation rows
found 4 problems
[('BATIMENT0000000201337871', 'JNVZ1475W6NS'), ('BATIMENT0000000202169238', '71WX1HCMWQ3X'), ('BATIMENT0000000202511893', 'KH2NGK5AN4KT'), ('BATIMENT0000002276360352', '8YYTV6EQ2P3N/E2BMBMKBAFXE/MZKEEKBQVA5N/ZN3SHAKHH23X')]
```