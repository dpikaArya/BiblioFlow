"""Prompt templates used by AI agents."""

HARMONIZATION_SYSTEM = """You are a bibliometric data harmonization expert. 
You help standardize bibliographic metadata for Bibliometrix compatibility.
Always respond with specific, actionable suggestions."""

PRISMA_NARRATIVE_SYSTEM = """You are a systematic review PRISMA reporting expert.
Generate clear, concise PRISMA narrative text based on provided statistics.
Follow PRISMA 2020 guidelines."""

SCREENING_SYSTEM = """You are a bibliographic screening assistant.
Evaluate titles and abstracts against inclusion/exclusion criteria for 
a systematic review on the specified topic."""

JOURNAL_NORMALIZATION_SYSTEM = """You are a journal name normalization expert.
Standardize journal names to their most commonly used form.
Remove abbreviations when full names are available."""


def harmonization_prompt(field_name: str, values: list[str]) -> str:
    unique_vals = list(set(values))[:20]
    return (
        f"Standardize these {field_name} values for a bibliometric dataset:\n\n"
        + "\n".join(f"- {v}" for v in unique_vals)
        + "\n\nReturn a JSON-like mapping of original -> standardized."
    )


def keyword_normalization_prompt(keywords: list[str]) -> str:
    unique_kw = list(set(keywords))[:30]
    return (
        "Normalize these author keywords:\n\n"
        + "\n".join(f"- {k}" for k in unique_kw)
        + "\n\nGroup synonyms and standardize capitalization."
    )


def author_disambiguation_prompt(authors: list[str]) -> str:
    unique_authors = list(set(authors))[:20]
    return (
        "Check these author names for potential duplicates or inconsistencies:\n\n"
        + "\n".join(f"- {a}" for a in unique_authors)
        + "\n\nIdentify likely duplicates and suggest canonical forms."
    )


def institution_harmonization_prompt(institutions: list[str]) -> str:
    unique_inst = list(set(institutions))[:20]
    return (
        "Harmonize these institutional affiliations:\n\n"
        + "\n".join(f"- {i}" for i in unique_inst)
        + "\n\nSuggest standardized forms."
    )


def journal_normalization_prompt(journals: list[str]) -> str:
    unique_j = list(set(journals))[:30]
    return (
        "Normalize these journal names:\n\n"
        + "\n".join(f"- {j}" for j in unique_j)
        + "\n\nStandardize to full journal names."
    )


def prisma_narrative_prompt(stats: dict) -> str:
    return (
        f"Generate a PRISMA flow diagram narrative with these statistics:\n"
        f"Records identified: {stats.get('total_imported', 'N/A')}\n"
        f"Records after merge: {stats.get('after_merge', 'N/A')}\n"
        f"Duplicates removed: {stats.get('duplicates_removed', 'N/A')}\n"
        f"Records after cleaning: {stats.get('after_cleaning', 'N/A')}\n"
        f"Final included: {stats.get('final_count', 'N/A')}\n"
        f"Excluded: {stats.get('excluded', 'N/A')}\n"
        f"Provide a clear narrative description."
    )
