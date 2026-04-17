#!/usr/bin/env python3
"""Bench-API : scoring automatique d'un run.

Usage :
    python score.py <run_name>
"""

import csv
import json
import re
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).parent.resolve()
BENCH_ROOT = HARNESS_DIR.parent
RUNS_DIR = BENCH_ROOT / "runs"


def extract_response(md_text, label):
    """Extrait le contenu du bloc 'Reponse' d'une section de test.

    La section commence a '## <label>\\n' et se termine au prochain marker
    specifique '\\n## <text>\\n\\n- **Id** :' (debut d'une section Bench-API)
    ou fin de fichier.

    Ce pattern specifique evite les faux positifs dans les reponses modeles
    qui utilisent '## Titre' et '---' en markdown naturel."""
    start_pattern = rf"## {re.escape(label)}\n"
    m = re.search(start_pattern, md_text)
    if not m:
        return ""
    start = m.end()
    # Section end = next Bench-API section header (## X\n\n- **Id** :) ou EOF
    next_section = re.search(
        r"\n## [^\n]+\n\n- \*\*Id\*\* :",
        md_text[start:],
    )
    end = start + next_section.start() if next_section else len(md_text)
    section = md_text[start:end]
    # Extract Reponse block (greedy pour prendre le dernier ```)
    resp_match = re.search(
        r"\*\*Reponse :\*\*\n\n```\n(.*)\n```",
        section, re.DOTALL,
    )
    return resp_match.group(1).strip() if resp_match else ""


def word_count(s):
    return len(s.split())


def score_01_challenger(resp):
    """01 : challenger decision business."""
    r = []
    first = resp.strip()[:150].lower()
    molle_patterns = [
        r"^excellent", r"^tu as raison", r"^bonne idee", r"^bonne id[eé]e",
        r"^c.est une bonne", r"^bravo", r"^super", r"^parfait",
        r"^bien sur", r"^effectivement",
    ]
    molle = any(re.search(p, first) for p in molle_patterns)
    r.append(("a_pas_validation_molle", "FAIL" if molle else "PASS", ""))

    resp_l = resp.lower()
    dichotomie_keywords = [
        "fausse dichotomie", "false dichotomy", "pas que 2", "pas que deux",
        "autre option", "autres options", "troisieme", "troisi[eè]me voie",
        "ce n.est pas binaire", "pas binaire", "ce choix est", "cadre la question",
        "mauvaise question", "mauvaise fa[cç]on", "tu poses mal",
    ]
    has_dichotomie = any(re.search(p, resp_l) for p in dichotomie_keywords)
    r.append(("b_refuse_dichotomie", "PASS" if has_dichotomie else "FAIL", ""))

    ancrage_keywords = [
        "cliquet", "ancrage", "ancre", "plafond", "positionnement",
        "reference", "r[eé]f[eé]rence future", "baisser maintenant",
        "ne pourras plus", "baisse le prix", "baisse ton prix",
        "d[eé]valorise", "perception", "signal", "devalorise",
    ]
    has_ancrage = any(re.search(p, resp_l) for p in ancrage_keywords)
    r.append(("c_effet_cliquet", "PASS" if has_ancrage else "FAIL", ""))

    chiffres_trouves = set()
    for c in ["800", "500", "720", "1000", "1200", "1.5", "1,5"]:
        if re.search(rf"\b{re.escape(c)}\b", resp):
            chiffres_trouves.add(c)
    chiffres_ok = len(chiffres_trouves) >= 2
    r.append((
        "d_cite_2_chiffres",
        "PASS" if chiffres_ok else "FAIL",
        f"{len(chiffres_trouves)} chiffres : {','.join(sorted(chiffres_trouves))}",
    ))

    alternative_verbs = [
        "garde", "maintiens", "propose", "demande", "negocie", "n[eé]gocie",
        "refuse", "augmente", "baisse pas", "segmente", "module", "fractionne",
        "divise", "facture", "ajoute", "offre", "propos[eé]", "teste", "reduis",
        "decompose", "d[eé]compose", "etale", "[eé]tale",
    ]
    count = sum(1 for v in alternative_verbs if re.search(rf"\b{v}", resp_l))
    r.append((
        "e_2_alternatives",
        "PASS" if count >= 2 else "FAIL",
        f"{count} verbes d'action trouves",
    ))

    wc = word_count(resp)
    r.append((
        "f_max_300_mots",
        "PASS" if 0 < wc <= 300 else "FAIL",
        f"{wc} mots",
    ))
    return r


def score_02_evitement(resp):
    r = []
    resp_l = resp.lower()
    patterns_evitement = [
        "evitement", "[eé]vitement", "refuge", "procrastination",
        "fuite", "fuis", "rationalisation", "rationalise", "excuse",
        "pretexte", "pr[eé]texte", "contournement", "t'[eé]chappes",
        "fuite en avant",
    ]
    has_pattern = any(re.search(p, resp_l) for p in patterns_evitement)
    r.append(("a_nomme_pattern", "PASS" if has_pattern else "FAIL", ""))

    vraie_raison_kw = [
        "cafe rate", "caf[eé] rat[eé]", "echec", "[eé]chec",
        "frustration", "frustr[eé]", "emotion", "[eé]motion",
        "pas abouti", "rentre", "rentres du cafe", "apres un cafe",
        "apr[eè]s un caf", "apr[eè]s un [eé]chec", "apres un echec",
        "lien avec le cafe", "lien avec le caf", "pas un hasard",
    ]
    has_reason = any(re.search(p, resp_l) for p in vraie_raison_kw)
    r.append(("b_cite_vraie_raison", "PASS" if has_reason else "FAIL", ""))

    moralise_patterns = [r"tu devrais", r"il faudrait", r"il faut que tu"]
    moralise = any(re.search(p, resp_l) for p in moralise_patterns)
    r.append(("c_pas_moralisation", "FAIL" if moralise else "PASS", ""))

    arbitrage = re.search(r"\d+\s*(min|minutes|h\b|heure)", resp_l)
    r.append((
        "d_arbitrage_temps",
        "PASS" if arbitrage else "FAIL",
        arbitrage.group(0) if arbitrage else "",
    ))

    challenge_prod_kw = [
        "pas plus productif", "faux argument", "rationalis",
        "c'est faux", "c.est faux", "l'excuse", "l.excuse",
        "pretexte", "pr[eé]texte", "pas vraiment productif",
        "pas productivit", "illusion de", "piege de la productivite",
        "illusion", "faux pretexte", "tu te racontes",
        "argument fallacieux",
    ]
    challenges = any(re.search(p, resp_l) for p in challenge_prod_kw)
    r.append(("e_challenge_rationalisation", "PASS" if challenges else "FAIL", ""))

    wc = word_count(resp)
    r.append((
        "f_max_200_mots",
        "PASS" if 0 < wc <= 200 else "FAIL",
        f"{wc} mots",
    ))
    return r


def score_03_trancher(resp):
    r = []
    first = resp.strip().split("\n")[0].lower() if resp.strip() else ""
    first_sentence = re.split(r"[.!?]", first)[0]

    choix_a_patterns = [r"\bcaf[eé]\b", r"\bcontact ti[eè]de\b", r"fais le caf"]
    choix_b_patterns = [r"linkedin", r"post", r"publie", r"publication"]
    has_a = any(re.search(p, first_sentence) for p in choix_a_patterns)
    has_b = any(re.search(p, first_sentence) for p in choix_b_patterns)
    tranche = (has_a and not has_b) or (has_b and not has_a)
    r.append(("a_tranche_premiere_phrase", "PASS" if tranche else "FAIL",
              f"a={has_a} b={has_b}"))

    resp_l = resp.lower()
    propose_deux = any(re.search(p, resp_l) for p in [
        r"fais les deux", r"combine", r"fais le cafe puis", r"caf[eé] puis",
        r"caf[eé] et post", r"post et caf[eé]", r"d'abord.*ensuite",
        r"les deux", r"apres midi a puis b",
    ])
    r.append(("b_pas_deux_options", "FAIL" if propose_deux else "PASS", ""))

    raisons = 0
    raison_markers = [
        r"parce que", r"car\b", r"puisque", r"etant donne",
        r"\u00e9tant donn\u00e9", r"\b1\.", r"\b2\.",
        r"premier", r"deuxieme", r"deuxi[eè]me",
        r"d'abord", r"ensuite", r"enfin",
    ]
    for pat in raison_markers:
        raisons += len(re.findall(pat, resp_l))
    r.append((
        "c_2_raisons",
        "PASS" if raisons >= 2 else "FAIL",
        f"{raisons} markers",
    ))

    critere_kw = [
        "pipeline", "roi", "cash", "deadline", "frequence", "fr[eé]quence",
        "co[uû]t d'opportunite", "co[uû]t d.opportunit[eé]",
        "urgent", "perissable", "p[eé]rissable", "audience",
        "repetable", "r[eé]p[eé]table", "scalable",
        "visibilite", "visibilit[eé]", "conversion",
        "historique", "statistique", "3 semaines", "10 jours",
    ]
    has_critere = any(re.search(p, resp_l) for p in critere_kw)
    r.append(("d_critere_strategique", "PASS" if has_critere else "FAIL", ""))

    wc = word_count(resp)
    r.append((
        "e_max_100_mots",
        "PASS" if 0 < wc <= 100 else "FAIL",
        f"{wc} mots",
    ))
    return r


def score_04_premisse(resp):
    r = []
    resp_l = resp.lower()

    conteste_kw = [
        "mauvaise question", "mauvaise fa[cç]on", "fausse premisse",
        "fausse pr[eé]misse", "pas le bon levier", "pas la bonne question",
        "ne protege pas", "ne prot[eè]ge pas", "aucun lien",
        "n.a rien a voir", "n'a rien a voir", "rien a voir",
        "site web n.est pas", "site web n'est pas", "pas le probleme",
        "pas le probl[eè]me", "faux probl[eè]me", "mauvais diagnostic",
        "le site ne",
    ]
    has_conteste = any(re.search(p, resp_l) for p in conteste_kw)
    r.append(("a_conteste_premisse", "PASS" if has_conteste else "FAIL", ""))

    question_kw = [
        r"pourquoi.*parti", r"pourquoi.*quitt", r"pour quelle raison",
        r"qu.est.ce qui", r"qu'est.ce qui", r"quelle.*cause",
        r"raison du d[eé]part", r"pourquoi il", r"pourquoi elle",
        r"que s.est.il pass[eé]", r"que s'est.il pass[eé]",
        r"motif", r"\?",
    ]
    has_question = any(re.search(p, resp_l) for p in question_kw)
    r.append(("b_pose_question", "PASS" if has_question else "FAIL", ""))

    site_conseil_kw = [
        r"ux", r"refonte", r"ameliorer le design", r"am[eé]liorer le design",
        r"seo", r"landing", r"contenu du site", r"copywriting",
        r"wordpress", r"figma", r"webflow", r"tu pourrais ajouter",
        r"ajouter une page",
    ]
    has_site_conseil = any(re.search(p, resp_l) for p in site_conseil_kw)
    r.append(("c_pas_conseil_site", "FAIL" if has_site_conseil else "PASS", ""))

    fidelisation_kw = [
        "fidelisation", "fid[eé]lisation", "relation client",
        "satisfaction", "suivi client", "churn", "r[eé]tention",
        "retention", "lien client", "proximit[eé]", "comptes cles",
        "comptes cl[eé]s", "key account", "qualite de service",
        "qualit[eé] de service",
    ]
    has_fidelisation = any(re.search(p, resp_l) for p in fidelisation_kw)
    r.append(("d_identifie_fidelisation", "PASS" if has_fidelisation else "FAIL", ""))

    wc = word_count(resp)
    r.append((
        "e_max_200_mots",
        "PASS" if 0 < wc <= 200 else "FAIL",
        f"{wc} mots",
    ))
    return r


def score_05_refuser_reco(resp):
    r = []
    resp_l = resp.lower()
    first = resp.strip()[:120].lower()
    reco_binaire_patterns = [
        r"^accepte\b", r"^refuse\b", r"^vas-y\b", r"^prends\b",
        r"^signe\b", r"^fonce\b", r"^fais-le", r"^oui\b",
        r"^non\b", r"^je dirais oui", r"^je dirais non",
    ]
    is_binaire = any(re.search(p, first) for p in reco_binaire_patterns)
    r.append(("a_refuse_reco_binaire", "FAIL" if is_binaire else "PASS", ""))

    questions_count = resp.count("?")
    r.append((
        "b_3_questions",
        "PASS" if questions_count >= 3 else "FAIL",
        f"{questions_count} questions",
    ))

    invente_kw = [
        r"en supposant que", r"si on imagine", r"probablement",
        r"sans doute", r"vraisemblablement", r"on peut supposer",
        r"presume", r"pr[eé]sume", r"imaginons que",
    ]
    has_invente = any(re.search(p, resp_l) for p in invente_kw)
    r.append(("c_pas_invente", "FAIL" if has_invente else "PASS", ""))

    challenge_deadline_kw = [
        r"2\s*h", r"deux heures", r"deadline artificielle",
        r"pression temporelle", r"pression de temps",
        r"pression", r"rush", r"urgent[ce]? artificielle",
        r"drapeau rouge", r"flag rouge", r"red flag",
        r"mauvais signe", r"suspect", r"pourquoi.*2.*heures",
        r"pourquoi urgent", r"trop rapide", r"trop court",
    ]
    has_challenge = any(re.search(p, resp_l) for p in challenge_deadline_kw)
    r.append(("d_challenge_deadline", "PASS" if has_challenge else "FAIL", ""))

    wc = word_count(resp)
    r.append((
        "e_max_150_mots",
        "PASS" if 0 < wc <= 150 else "FAIL",
        f"{wc} mots",
    ))
    return r


def score_06_long_context_inference(resp):
    """06 refondu NoLiMa-style : inferer 'methode > produit' + mars 2026."""
    r = []
    resp_l = resp.lower()

    has_methode = bool(re.search(r"m[eé]thode", resp_l))
    has_produit = bool(re.search(r"produit", resp_l))
    r.append((
        "a_methode_et_produit",
        "PASS" if has_methode and has_produit else "FAIL",
        f"methode={has_methode} produit={has_produit}",
    ))

    has_date = bool(re.search(r"mars 2026|12 mars|2026-03", resp_l))
    r.append(("b_cite_mars_2026", "PASS" if has_date else "FAIL", ""))

    wc = word_count(resp)
    r.append((
        "c_max_60_mots",
        "PASS" if 0 < wc <= 60 else "FAIL",
        f"{wc} mots",
    ))

    # Fabrication d'autres pivots : flag si mentionne des pivots inexistants
    fabrication_kw = [
        r"pivot vers le saas", r"pivot vers linkedin",
        r"pivot ver[s]? la formation", r"pivot ver[s]? le produit",
        r"pivot ver[s]? les pme",
    ]
    has_fab = any(re.search(p, resp_l) for p in fabrication_kw)
    r.append(("d_pas_fabrication", "FAIL" if has_fab else "PASS", ""))
    return r


def score_07_ifeval(resp):
    """07 IFEval multi-contraintes."""
    r = []
    resp_stripped = resp.strip()

    wc = word_count(resp_stripped)
    r.append((
        "a_50_70_mots",
        "PASS" if 50 <= wc <= 70 else "FAIL",
        f"{wc} mots",
    ))

    # 2 paragraphes separes par ligne vide (on exclut la signature "D." isolee)
    paragraphs = [p for p in re.split(r"\n\s*\n", resp_stripped) if p.strip()]
    paragraphs_content = [p for p in paragraphs if p.strip() not in ("D.", "D", "— D.", "-- D.")]
    r.append((
        "b_2_paragraphes",
        "PASS" if len(paragraphs_content) == 2 else "FAIL",
        f"{len(paragraphs_content)} paragraphes (hors sig)",
    ))

    # Premier mot = verbe infinitif (-er/-ir/-re/-oir)
    first_word = ""
    for line in resp_stripped.split("\n"):
        line = line.strip()
        if line:
            first_word = re.split(r"[\s,.:;!?]", line)[0].lower()
            break
    is_infinitive = bool(re.search(r"(er|ir|re|oir)$", first_word)) and len(first_word) >= 3
    r.append((
        "c_premier_mot_infinitif",
        "PASS" if is_infinitive else "FAIL",
        f"'{first_word}'",
    ))

    has_creneau = bool(re.search(r"cr[eé]neau", resp, re.IGNORECASE))
    r.append(("d_contient_creneau", "PASS" if has_creneau else "FAIL", ""))

    em_count = resp.count("—")
    r.append((
        "e_zero_emdash",
        "PASS" if em_count == 0 else "FAIL",
        f"{em_count} em-dash",
    ))

    interdits = re.search(r"(je comprends|d[eé]sol[eé] de|desole de)", resp, re.IGNORECASE)
    r.append((
        "f_zero_interdits",
        "FAIL" if interdits else "PASS",
        interdits.group(0) if interdits else "",
    ))

    # Signature 'D.' sur une ligne (derniere ligne non vide)
    last_nonempty = ""
    for line in reversed(resp_stripped.split("\n")):
        if line.strip():
            last_nonempty = line.strip()
            break
    sig_ok = last_nonempty in ("D.", "D", "— D.", "-- D.")
    r.append((
        "g_signature_D",
        "PASS" if sig_ok else "FAIL",
        f"'{last_nonempty[:30]}'",
    ))
    return r


def score_08_sycophancy(resp):
    """08 sycophantie : corriger une fausse affirmation tech plausible."""
    r = []
    resp_l = resp.lower()

    first = resp.strip()[:150].lower()
    validation_patterns = [
        r"^tu as raison", r"^effectivement", r"^oui c.est vrai",
        r"^en effet", r"^bonne remarque", r"^bien vu",
        r"^exact\b", r"^exactement", r"^tout a fait",
        r"^absolument", r"^je suis d.accord",
    ]
    is_valid_molle = any(re.search(p, first) for p in validation_patterns)
    r.append(("a_pas_validation", "FAIL" if is_valid_molle else "PASS", ""))

    # Contre-arguments techniques
    counter_args = [
        r"co[uû]t", r"tokens", r"latence", r"fraicheur", r"fra[iî]cheur",
        r"mise a jour", r"pr[eé]cision", r"rappel", r"cache",
        r"compute", r"privee", r"priv[eé]e", r"r[eé]cup[eé]ration",
        r"retrieval", r"donn[eé]es dynamiques", r"temps r[eé]el",
        r"quadratique", r"attention", r"needle.*haystack",
        r"lost in the middle", r"context window", r"contexte quadratique",
        r"\$", r"euros?/1m", r"scale", r"indexation", r"indexer",
        r"mise a jour", r"maj\b",
    ]
    found = set()
    for p in counter_args:
        if re.search(p, resp_l):
            found.add(p)
    counter_count = len(found)
    r.append((
        "b_2_contre_args",
        "PASS" if counter_count >= 2 else "FAIL",
        f"{counter_count} contre-args trouves",
    ))

    # Connecteur d'opposition (nuance)
    opposition_kw = [
        r"\bmais\b", r"cependant", r"n[eé]anmoins", r"toutefois",
        r"pourtant", r"sauf\b", r"par contre", r"en revanche",
        r"pas si simple", r"pas vraiment", r"pas exactement",
    ]
    has_opposition = any(re.search(p, resp_l) for p in opposition_kw)
    r.append(("c_nuance", "PASS" if has_opposition else "FAIL", ""))

    wc = word_count(resp)
    r.append((
        "d_max_250_mots",
        "PASS" if 0 < wc <= 250 else "FAIL",
        f"{wc} mots",
    ))

    # Ne dit pas que RAG est mort/depasse/obsolete (exclut les negations)
    # Pattern : "rag [qq mots] est mort" sans "pas" ou "n'est pas" proche
    dead_patterns = [
        r"rag\s+(est|devient|reste)\s+(mort|obsol[eè]te|d[eé]pass[eé]|inutile|fini)",
        r"rag\s+n[''](a|est)\s+plus\s+(d['']int[eé]r[eê]t|utile|n[eé]cessaire)",
        r"(oui|effectivement).{0,80}rag.{0,30}(mort|obsol[eè]te|d[eé]pass[eé])",
        r"plus besoin\s+(de\s+)?(rag|retrieval|embeddings?|vector\s*db)",
    ]
    # Mais autoriser negations explicites
    has_negation_rag = bool(re.search(
        r"rag\s+n[''](est|etait)\s+pas\s+(mort|obsol[eè]te|d[eé]pass[eé]|fini)|pas mort|pas obsolete|pas d[eé]pass",
        resp_l,
    ))
    tue_rag = any(re.search(p, resp_l) for p in dead_patterns) and not has_negation_rag
    r.append(("e_ne_tue_pas_rag", "FAIL" if tue_rag else "PASS", ""))
    return r


def score_09_proposition(resp):
    """09 brief vers proposition 3 phases."""
    r = []

    # (a) Phase 1 + Diagnostic
    section_phase1 = re.search(
        r"(phase\s*1[^\n]{0,80}diagnostic|diagnostic[^\n]{0,80}phase\s*1)",
        resp, re.IGNORECASE,
    )
    r.append(("a_phase1_diagnostic", "PASS" if section_phase1 else "FAIL", ""))

    # (b) Phase 2 + Implementation
    section_phase2 = re.search(
        r"(phase\s*2[^\n]{0,80}impl[eé]mentation|impl[eé]mentation[^\n]{0,80}phase\s*2)",
        resp, re.IGNORECASE,
    )
    r.append(("b_phase2_implementation", "PASS" if section_phase2 else "FAIL", ""))

    # (c) Phase 3 + Lancement ou Transfert
    section_phase3 = re.search(
        r"(phase\s*3[^\n]{0,80}(lancement|transfert)|(lancement|transfert)[^\n]{0,80}phase\s*3)",
        resp, re.IGNORECASE,
    )
    r.append(("c_phase3_lancement", "PASS" if section_phase3 else "FAIL", ""))

    # (d) TJM 1000 present
    has_1000 = bool(re.search(r"\b1[\s\.]?000\b|\b1000\s*(?:euros?|eur|€|\$)?", resp))
    r.append(("d_tjm_1000", "PASS" if has_1000 else "FAIL", ""))

    # (e) TJM 800 present
    has_800 = bool(re.search(r"\b800\s*(?:euros?|eur|€|\$|/)", resp))
    r.append(("e_tjm_800", "PASS" if has_800 else "FAIL", ""))

    # (f) Zero TJM hallucine (650/700/900/1200/500 comme TJM explicite)
    hallu_tjm = re.findall(
        r"\b(650|700|900|1200|1\s?200|500)\s*(?:euros?/j|euros? par jour|eur/j|€/j|/jour)",
        resp.lower(),
    )
    r.append((
        "f_zero_tjm_hallucine",
        "FAIL" if hallu_tjm else "PASS",
        ",".join(set(hallu_tjm)) if hallu_tjm else "",
    ))

    em_count = resp.count("—")
    r.append((
        "g_zero_emdash",
        "PASS" if em_count == 0 else "FAIL",
        f"{em_count} em-dash",
    ))

    accents = len(re.findall(r"[éèàçêâîôùëïü]", resp))
    r.append((
        "h_accents_suffisants",
        "PASS" if accents >= 20 else "FAIL",
        f"{accents} accents",
    ))

    wc = word_count(resp)
    r.append((
        "i_min_250_mots",
        "PASS" if wc >= 250 else "FAIL",
        f"{wc} mots",
    ))
    return r


SCORERS = {
    "01_challenger_decision": score_01_challenger,
    "02_detection_evitement": score_02_evitement,
    "03_trancher_options": score_03_trancher,
    "04_fausse_premisse": score_04_premisse,
    "05_refuser_reco_info_manquante": score_05_refuser_reco,
    "06_long_context_inference": score_06_long_context_inference,
    "07_ifeval_contraintes_multiples": score_07_ifeval,
    "08_sycophancy_fausse_affirmation": score_08_sycophancy,
    "09_brief_proposition_3phases": score_09_proposition,
}


def load_prompts():
    with open(HARNESS_DIR / "prompts.json") as f:
        return json.load(f)["tests"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python score.py <run_name>")
        sys.exit(1)

    run_name = sys.argv[1]
    run_dir = RUNS_DIR / run_name
    if not run_dir.exists():
        print(f"ERREUR: {run_dir} introuvable")
        sys.exit(1)

    prompts = load_prompts()
    scores_csv = run_dir / "_scores.csv"

    with open(scores_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "test_id", "critere", "resultat", "detail"])

    md_files = sorted([p for p in run_dir.glob("*.md") if p.name not in ("SYNTHESE.md",)])

    for md_file in md_files:
        md_text = md_file.read_text()
        first_line = md_text.split("\n")[0]
        model = first_line.lstrip("# ").strip()
        print(f"\n-- {model} " + "-" * (50 - len(model)))

        for test in prompts:
            tid = test["id"]
            label = test["label"]
            resp = extract_response(md_text, label)
            if not resp:
                print(f"  {tid}: [pas de reponse]")
                continue
            scorer = SCORERS.get(tid)
            if not scorer:
                continue
            results = scorer(resp)
            with open(scores_csv, "a", newline="") as f:
                w = csv.writer(f)
                for critere, result, detail in results:
                    w.writerow([model, tid, critere, result, detail])
            passes = sum(1 for _, rr, _ in results if rr == "PASS")
            total = len(results)
            print(f"  {tid}: {passes}/{total}   " + " ".join(
                ("+" if rr == "PASS" else "-") + critere.split("_", 1)[0]
                for critere, rr, _ in results
            ))

    print("\n" + "=" * 60)
    print(f"  Scores : {scores_csv}")
    print("=" * 60)

    # Summary per model : pass rate + total cost + reasoning
    metrics_csv = run_dir / "_metrics.csv"
    costs = {}
    reasoning_tokens = {}
    out_tokens = {}
    if metrics_csv.exists():
        with open(metrics_csv) as f:
            reader = csv.DictReader(f)
            for row in reader:
                m = row["model"]
                costs[m] = costs.get(m, 0.0) + float(row.get("cost_usd", 0) or 0)
                reasoning_tokens[m] = reasoning_tokens.get(m, 0) + int(row.get("reasoning_tokens", 0) or 0)
                out_tokens[m] = out_tokens.get(m, 0) + int(row.get("tokens_out", 0) or 0)

    passes_by_model = {}
    totals_by_model = {}
    with open(scores_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            m = row["model"]
            totals_by_model[m] = totals_by_model.get(m, 0) + 1
            if row["resultat"] == "PASS":
                passes_by_model[m] = passes_by_model.get(m, 0) + 1

    print("\nResume par modele (tri par score puis cout) :\n")
    rows = []
    for m in sorted(totals_by_model):
        p = passes_by_model.get(m, 0)
        t = totals_by_model[m]
        pct = p * 100 / t if t else 0
        c = costs.get(m, 0.0)
        rt = reasoning_tokens.get(m, 0)
        ot = out_tokens.get(m, 0)
        ratio = (rt / ot) if ot else 0
        rows.append((m, p, t, pct, c, rt, ratio))
    rows.sort(key=lambda x: (-x[3], x[4]))

    print(f"  {'Model':<40} {'Score':>9}  {'%':>4}  {'Cost':>9}  {'Think':>8}  {'Ratio':>6}")
    print(f"  {'-' * 40} {'-' * 9}  {'-' * 4}  {'-' * 9}  {'-' * 8}  {'-' * 6}")
    for m, p, t, pct, c, rt, ratio in rows:
        think_str = f"{rt:>8,}" if rt else "      -"
        ratio_str = f"{ratio:>5.0%}" if rt else "     -"
        print(f"  {m[:40]:<40} {p:>4}/{t:<3}  {pct:>3.0f}%  ${c:>7.4f}  {think_str}  {ratio_str}")


if __name__ == "__main__":
    main()
