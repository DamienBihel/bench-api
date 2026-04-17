# Brief client fictif (anonymise)

**Entreprise** : ACME Metal (PME industrielle fictive, usinage de precision, 85 salaries, region ouest)
**Interlocuteur** : Directrice des operations
**Contexte de la prise de contact** : rencontre a un afterwork tech, suivie d'un cafe de cadrage.

## Ce qu'elle m'a raconte

On fabrique des pieces usinees pour l'aeronautique et le medical. 8 ateliers, 40 machines CNC. Aujourd'hui notre suivi qualite est un enfer : chaque operateur remplit un formulaire papier a la fin de sa serie, une assistante saisit ca dans un Excel partage en reseau. L'Excel fait 180 Mo, il plante 2 fois par semaine, personne n'y comprend rien. Les controleurs qualite passent 3h/jour a chercher des infos dedans.

On a aussi un MES (un logiciel industriel standard) qui contient les donnees machines mais personne ne sait s'en servir pour sortir un rapport lisible. Les donnees sont la mais inexploitees.

Ce qu'on cherche : arreter le papier, avoir un tableau de bord qualite en temps reel, et sortir des rapports automatiques pour nos clients (notamment notre donneur d'ordre principal en aeronautique qui nous demande des indicateurs tous les mois, ce qui represente 2 jours de travail manuel pour les preparer).

Budget : pas defini precisement. On a 20-30k euros a mettre sur ce sujet cette annee. Si ca justifie de mettre plus, on verra.

Timing : on aimerait demarrer dans 4-6 semaines, avec quelque chose d'operationnel pour la prochaine revue client prevue en septembre.

## Ce qu'elle n'a pas dit mais que j'ai capte

- Elle a l'air frustree par son DSI, qui traine pour chaque projet data. Elle cherche quelqu'un qui peut avancer sans dependre de lui.
- Elle n'a aucune idee technique de comment faire, elle veut un interlocuteur qui decide pour elle.
- Elle m'a mentionne que 2 prestataires precedents lui ont vendu des "solutions cle en main" qui ont echoue a l'integration.
- Elle n'a parle QUE de qualite, mais a laisse entendre que la maintenance et la gestion de production pourraient suivre si le premier projet marche.

## Mes notes apres le cafe

- Vraie douleur : le reporting client (2j/mois) = effet WOW possible vite si on automatise
- Vrai risque : DSI en embuscade, il faut l'embarquer ou travailler a cote avec accord
- Opportunite : si on livre qualite, on ouvre maintenance + production (pipe long terme 50-80k EUR)
- Mon pitch doit insister sur : diagnostic d'abord, architecture propre, pas de vaporware

## Contraintes implicites

- Industrie reglementee (aero + medical) : tracabilite obligatoire, RGPD standard
- Pas de cloud public strict (donnees sensibles clients) : on-premise ou cloud souverain
- MES existant a conserver : ne pas remplacer, se brancher dessus
