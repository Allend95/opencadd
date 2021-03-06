"""
Defines easy programmatic access for any entry point
"""

from .engines.theseus import TheseusAligner
from .engines.mmligner import MMLignerAligner
from .engines.mda import MDAnalysisAligner
from ..core import Structure


METHODS = {
    "theseus": TheseusAligner,
    "mmligner": MMLignerAligner,
    "mda": MDAnalysisAligner,
}


def align(structures, method=TheseusAligner, **kwargs):
    """
    Main entry point for our project

    Parameters
    ----------
    structures : list of opencadd.core.Structure objects
        First one will be the targer to which the rest are aligned
    method : BaseAligner-like
        Usually a subclass of BaseAligner. This will be passed ``**kwargs``. This class
        MUST define `.calculate()`.

    Returns
    -------
    dict
        superposed models
        rmsd
        metadata
    """
    aligner = method(**kwargs)
    assert all(isinstance(s, Structure) for s in structures)
    reference, *mobiles = structures
    results = []
    for mobile in mobiles:
        result = aligner.calculate([reference, mobile])
        results.append(result)

    return results
