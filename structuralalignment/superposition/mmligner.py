"""
MMLigner (Collier et al., 2017) works by minimizing the ivalue of the alignment. The ivalue is based on
the Minimum Message Length framework (Wallace and Boulton, 1968; Wallace, 2005), a Bayesian framework for
statistical inductive inference. The ivalue represents the hypothetical minimum message length needed to transmit
the computed alignment losslessly (Shannon, 1948).
Using the ivalue measure, the algorithm creates crude-but-effective strucural alignments rapidly to act as seeds.
These seeds are iteratively refined over an Expectation-Maximization approach using the I-value criterion.
By substracting the ivalue from the null model, the statistical significance of the alignment can be computed. If the
difference is positive, the alignment is significant.

Collier, J.H., Allison, L., Lesk A.M., Stuckey, P.J., Garcia de la Banda , M., Konagurthu, A.S. (2017)
Statistical inference of protein structural alignments using information and compression.
Bioinformatics, 33(7), 1005-1013

Wallace,C.S. and Boulton,D.M. (1968) An information measure for classification.
Comput. J., 11, 185–194.

Wallace,C.S. (2005) Statistical and Inductive Inference Using MinimumMessage Length.
Information Science and Statistics. SpringerVerlag, New York, NY.

Shannon,C.E. (1948) A mathematical theory of communication.
Bell Syst.Tech. J., 27, 379–423.
"""

import sys
import subprocess
from copy import deepcopy

import numpy as np
import atomium
import biotite.sequence.io.fasta as fasta

from .base import BaseAligner
from ..utils import enter_temp_directory


class MMLignerAligner(BaseAligner):
    """
    Wraps mmligner to superpose two protein structures

    Parameters
    ----------
    executable : str
        Path to the mmligner executable file
    """

    def __init__(self, executable=None):
        if executable is None:
            executable = "mmligner64.exe" if sys.platform.startswith("win") else "mmligner"
        self.executable = executable

    # pylint: disable=arguments-differ
    def _calculate(self, structures, **kwargs):
        """
        Calculates the superposition of two protein structures.

        It is called by BaseAligner.calculate().

        Parameters
        ----------
        structures: [array like, array like]
            Sequences of two protein structures of same length

        Returns
        -------
        dict
            As returned by ``._parse(output)``.

            - ``superposed`` ([atomium.model, atomium.model]): superposed structures
            - ``scores`` (dict):
                - ``rmsd`` (float): RMSD value of the alignment
                - ``score`` (float): ivalue of the alignment
                - ``coverage`` (float): coverage of the alignment
            - ``metadata`` (dict):
                - ``alignment``: (biotite.alignment): computed alignment
        """

        with enter_temp_directory(remove=False) as (cwd, tmpdir):
            print(tmpdir)
            path1, path2 = self._edit_pdb(structures)
            output = subprocess.check_output(
                [self.executable, path1, path2, "-o", "temp", "--superpose"]
            )
            # We need access to the temporary files at parse time!
            result = self._parse_metadata(output.decode())
            copies = [deepcopy(structure) for structure in structures]
            superposed_models = self._calculate_transformed(copies, result["metadata"])
            result.update({"superposed": superposed_models})
        return result

    def _parse_metadata(self, output):
        """
        retrieves rmsd, score and metadata from the output of the mmligner subprocess

        Parameters
        ----------
        output: bytes
            string of bytes containing the stdout of the mmligener call

        Returns
        -------
        dict
            As returned by ``._parse(output)``.
            - ``scores`` (dict):
                - ``rmsd`` (float): RMSD value of the alignment
                - ``score`` (float): ivalue of the alignment
                - ``coverage`` (float): coverage of the alignment
            - ``metadata`` (dict):
                - ``alignment``: (biotite.alignment): computed alignment
        """
        lines = iter(output.splitlines())
        print(output)
        for line in lines:
            if line.startswith("RMSD"):
                rmsd = float(line.split()[2])
            elif line.startswith("Coverage"):
                coverage = float(line.split()[2])
            elif line.startswith("I(A & <S,T>)"):
                ivalue = float(line.split()[4])
            elif "Print Centers of Mass of moving set:" in line:
                moving_com = np.array([float(x) for x in next(lines).split()])
            elif "Print Centers of Mass of fixed set:" in line:
                fixed_com = np.array([float(x) for x in next(lines).split()])
            elif "Print Rotation matrix" in line:
                rotation = [[float(x) for x in next(lines).split()] for _ in range(3)]

        translation = fixed_com - moving_com
        alignment = fasta.FastaFile()
        alignment.read("temp__1.afasta")
        return {
            "scores": {"rmsd": rmsd, "score": ivalue, "coverage": coverage},
            "metadata": {
                "alignment": alignment,
                "rotation": rotation,
                "translation": translation,
            },
        }

    def _calculate_transformed(self, structures, metadata):
        """
        Parse back output PDBs and construct updated atomium models

        Parameters
        ----------
        structures: list of atomium.Model
            Original input structures

        Return
        ------
        list of atomium.Model
            Input structures with updated coordinates
        """
        ref, original_mobile, *_ = structures
        # assert len(ref.atoms()) == len(atomium.open("structure1.pdb").model.atoms())  # quick check
        # with open("p_superposed__1.pdb") as f:
        #     for line in f:
        #         if "REMARK" in line and "Rotation:" in line:
        #             rotation = np.reshape([float(x) for x in line.split(":")[1].split()], (-1, 3))
        #         if "REMARK" in line and "Translation:" in line:
        #             translation = [float(x) for x in line.split(":")[1].split()]
        translation = metadata["translation"]
        rotation = metadata["rotation"]

        atomium_translation = original_mobile.center_of_mass - ref.center_of_mass
        original_mobile.translate(*translation)
        original_mobile.transform(rotation)
        original_mobile.translate(ref.center_of_mass - original_mobile.center_of_mass)

        return ref, original_mobile

    def ivalue(self, structures, alignment):
        """
        computes the score and rmsd for a given alignment of two structures by calling mmligner as a subprocess

        Parameters
        ----------
        structures: [array like, array like]
            sequences of two protein structures of same length
        alignment: array like
            alignment of the given two sequences

        Returns
        -------
        dict
            As returned by ``._parse(output)``.

            - ``superposed`` ([atomium.model, atomium.model]): superposed structures
            - ``scores`` (dict):
                - ``rmsd`` (float): RMSD value of the alignment
                - ``score`` (float): ivalue of the alignment
                - ``coverage`` (float): coverage of the alignment
            - ``metadata`` (dict):
                - ``alignment``(biotite.alignment): computed alignment
        """

        with enter_temp_directory() as (cwd, tmpdir):
            path1, path2 = self._edit_pdb(structures)
            output = subprocess.check_output(
                [self.executable, path1, path2, "--ivalue", alignment.to_fasta()]
            )
            # We need access to the temporary files at parse time!
            result = self._parse(output)

        return result

    def _edit_pdb(self, structures, path=("./structure1.pdb", "./structure2.pdb")):
        """
        function to write atomium protein models to pdb readable by mmligner

        Parameters
        ----------
        structures: [array like, array like]
            two protein structures

        path: [str, str], Optional=["structure1.pdb, "structure2.pdb"]
            Path where the pdbs should be written

        Returns
        -------
        str, str
            Paths of both structures

        .. note::

            This is a temporary workaround to fix issue #9 at:
            https://github.com/volkamerlab/structuralalignment/issues/9
        """
        assert len(path) == 2

        structures[0].save(path[0])
        structures[1].save(path[1])

        for i in range(len(path)):
            pdb = []
            with open(path[i], "r") as infile:
                pdb = infile.readlines()
                for j in range(1, len(pdb)):
                    if pdb[j].startswith("TER"):
                        pdb[j] = pdb[j].split()[0] + "    " + pdb[j - 1].split()[1] + "\n"

            self._write_pdb(path[i], pdb)

        return path[0], path[1]

    def _write_pdb(self, path, pdb):
        """
        function to write atomium protein models to pdb readable by mmligner

        Parameters
        ----------
        path: str
            Path where the pdb should be written

        pdb: array-like
            edited pdb file

        .. note::

            This is a temporary workaround to fix issue #9 at:
            https://github.com/volkamerlab/structuralalignment/issues/9
        """
        with open(path, "w") as outfile:
            for line in pdb:
                outfile.write(line)
