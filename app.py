import gc
import io
import uuid
import zipfile
from pathlib import Path

import streamlit as st
from Bio import PDB


LARGE_UPLOAD_WARN_MB = 100


def convert_cif_bytes_to_pdb_bytes(cif_bytes: bytes) -> bytes:
    parser = PDB.MMCIFParser(QUIET=True)
    structure = parser.get_structure(
        "structure", io.StringIO(cif_bytes.decode("utf-8"))
    )
    out = io.StringIO()
    writer = PDB.PDBIO()
    writer.set_structure(structure)
    writer.save(out)
    return out.getvalue().encode("utf-8")


st.set_page_config(
    page_title="AlphaFold Server CIF to PDB Converter",
    page_icon=":sparkles:",
    layout="centered",
    initial_sidebar_state="auto",
)

st.title("AlphaFold Server CIF to PDB Converter")
st.markdown(
    """
    Welcome to the **AlphaFold Server CIF to PDB Converter!**
    Upload one or more ZIP files downloaded from the
    [AlphaFold server](https://alphafoldserver.com/). The app reads each
    ZIP, converts every **.cif** file inside to **.pdb** format, and packs
    everything back into a single ZIP for download.
    """
)

st.session_state.setdefault("uploaded_files_key", str(uuid.uuid4()))
st.session_state.setdefault("file_name_key", str(uuid.uuid4()))
st.session_state.setdefault("converting", False)

uploaded_files = st.file_uploader(
    "Upload AlphaFold Server ZIPs",
    type="zip",
    accept_multiple_files=True,
    key=st.session_state["uploaded_files_key"],
    disabled=st.session_state["converting"],
)

output_folder_name = st.text_input(
    "Output ZIP name",
    "converted_files.zip",
    key=st.session_state["file_name_key"],
    disabled=st.session_state["converting"],
)

if uploaded_files:
    total_mb = sum(f.size for f in uploaded_files) / (1024 * 1024)
    if total_mb > LARGE_UPLOAD_WARN_MB:
        st.warning(
            f"Large upload: {total_mb:.1f} MB across {len(uploaded_files)} file(s). "
            "Conversion may be slow and may hit shared-hosting resource limits."
        )
else:
    st.info("Please upload one or more ZIP files.")

btn_empty = st.empty()

if btn_empty.button(
    "Convert", use_container_width=True, disabled=not uploaded_files
):
    st.session_state["converting"] = True
    st.rerun()

if st.session_state["converting"]:
    st.session_state["converting"] = False

    output_buffer = io.BytesIO()
    total = len(uploaded_files)
    converted = 0
    failed = []

    with st.status(
        f"Converting {total} ZIP file(s)...", expanded=True
    ) as status:
        with zipfile.ZipFile(
            output_buffer, "w", zipfile.ZIP_DEFLATED
        ) as out_zip:
            for i, uploaded_file in enumerate(uploaded_files, start=1):
                folder_name = Path(uploaded_file.name).stem
                status.write(f"[{i}/{total}] {uploaded_file.name}")

                with zipfile.ZipFile(uploaded_file, "r") as in_zip:
                    for member in in_zip.infolist():
                        if member.is_dir():
                            continue
                        # Path(...).name strips any directory prefix,
                        # neutralizing zip-slip attempts.
                        member_name = Path(member.filename).name
                        if not member_name:
                            continue
                        data = in_zip.read(member)
                        out_zip.writestr(
                            f"{folder_name}/{member_name}", data
                        )
                        if member_name.lower().endswith(".cif"):
                            try:
                                pdb_bytes = convert_cif_bytes_to_pdb_bytes(data)
                                pdb_name = Path(member_name).with_suffix(".pdb").name
                                out_zip.writestr(
                                    f"{folder_name}/{pdb_name}", pdb_bytes
                                )
                                converted += 1
                            except Exception as e:
                                failed.append(f"{folder_name}/{member_name}")
                                status.write(f"  ! Failed to convert {member_name}: {e}")
                        del data
                gc.collect()

        label = f"Done — converted {converted} .cif file(s) from {total} ZIP(s)."
        if failed:
            label += f" {len(failed)} failed."
        status.update(label=label, state="complete")

    output_buffer.seek(0)
    if btn_empty.download_button(
        label="Download",
        data=output_buffer,
        file_name=output_folder_name,
        mime="application/zip",
        type="primary",
        use_container_width=True,
    ):
        st.session_state["uploaded_files_key"] = str(uuid.uuid4())
        st.session_state["file_name_key"] = str(uuid.uuid4())
        st.rerun()
