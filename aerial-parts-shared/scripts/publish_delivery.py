"""Publish a reviewed preview only after explicit user confirmation."""
from __future__ import annotations
import argparse, csv, os, shutil, uuid
from datetime import datetime, timezone
from pathlib import Path
from pipeline_common import load_json_object, sha256_file, write_json_object

_RENDERERS = {"ffmpeg", "ffmpeg+remotion"}

def _file(path, label):
    if path is None or not Path(path).is_file(): raise ValueError(f"{label} file does not exist: {path}")
    return Path(path).resolve()

def _hash(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label} must be a 64 lowercase hexadecimal hash")
    return value

def _archive(path):
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); candidate=path.with_name(f"{path.stem}.previous-{stamp}{path.suffix}"); n=2
    while candidate.exists(): candidate=path.with_name(f"{path.stem}.previous-{stamp}-{n}{path.suffix}"); n+=1
    return candidate

def _report(preview, path, edit):
    report=load_json_object(path)
    if _hash(report.get("preview_sha256"), "edit report preview_sha256") != sha256_file(preview): raise ValueError("edit report preview_sha256 does not match preview")
    edit_hash=_hash(report.get("edit_sha256"), "edit report edit_sha256")
    _hash(report.get("look_sha256"), "edit report look_sha256")
    if not isinstance(report.get("look_id"),str) or not report["look_id"]: raise ValueError("edit report look_id must be a non-empty string")
    if report.get("renderer") not in _RENDERERS: raise ValueError("edit report renderer must be ffmpeg or ffmpeg+remotion")
    if edit is not None:
        edit_path=_file(edit,"edit")
        if sha256_file(edit_path) != edit_hash: raise ValueError("edit report edit_sha256 does not match edit")
        edit_value=load_json_object(edit_path)
        if report["look_id"] != edit_value.get("look_id"): raise ValueError("edit report look_id does not match edit")
        if str(edit_value.get("look_id", "")).lower().endswith(".cube") and sha256_file(_file(edit_value["look_id"],"approved LUT")) != report["look_sha256"]: raise ValueError("edit report look_sha256 does not match approved LUT")
    return report

def _overlap(a,b): return a == b or a in b.parents or b in a.parents

def _handoff_plan(library_path, edit_path, music_path, subtitle_path, cube_path, storyboard_path):
    library=load_json_object(_file(library_path,"library")); edit=load_json_object(_file(edit_path,"edit"))
    if not isinstance(library.get("parts"),list) or not isinstance(edit.get("timeline"),list): raise ValueError("library parts and edit timeline must be arrays")
    parts={}
    for part in library["parts"]:
        if not isinstance(part,dict) or not isinstance(part.get("id"),str) or not isinstance(part.get("file"),str): raise ValueError("library parts must provide id and file")
        # Do not inspect parts[].src: handoff is built only from extracted parts[].file.
        parts[part["id"]]=_file(Path(part["file"]),f"part {part['id']}")
    assets=[]; names={}; rows=[]
    for item in edit["timeline"]:
        if not isinstance(item,dict) or not isinstance(item.get("part_id"),str): raise ValueError("edit timeline items must provide part_id")
        source=parts.get(item["part_id"])
        if source is None: raise ValueError(f"edit references unknown part_id: {item['part_id']}")
        prior=names.get(source.name)
        if prior is not None and prior != source: raise ValueError(f"used part filenames collide: {source.name}")
        if prior is None: names[source.name]=source; assets.append(("video",source.name,source))
        rows.append({k:item.get(k,"") for k in ("part_id","source_in","source_out","cut_at","transition")})
    music=_file(music_path,"music"); assets.append(("audio",music.name,music))
    for folder,path,suffix,label,name in (("subtitles",subtitle_path,".srt","subtitle",None),("lut",cube_path,".cube","cube",None),("",storyboard_path,None,"storyboard","storyboard.jpg")):
        if path is not None:
            asset=_file(path,label)
            if suffix and asset.suffix.lower()!=suffix: raise ValueError(f"{label} must be a {suffix} file")
            assets.append((folder,name or asset.name,asset))
    return assets,rows

def _approved_cube_for_handoff(edit_path, report, cube_path):
    edit=load_json_object(_file(edit_path,"edit")); look_id=edit.get("look_id")
    if not isinstance(look_id,str) or not look_id: raise ValueError("edit look_id must be a non-empty string")
    if look_id.lower().endswith(".cube"):
        selected=_file(Path(look_id),"approved LUT")
        if sha256_file(selected) != report["look_sha256"]: raise ValueError("edit report look_sha256 does not match approved LUT")
        if cube_path is not None and _file(cube_path,"cube") != selected: raise ValueError("--cube must match the approved custom LUT")
        return selected
    if cube_path is not None: raise ValueError("--cube is not allowed for a built-in look")
    return None

def _write_handoff(dest,assets,rows):
    temp=dest.with_name(f".{dest.name}.publishing-{uuid.uuid4().hex}")
    try:
        (temp/"video").mkdir(parents=True)
        for folder,name,source in assets:
            target=temp/folder/name if folder else temp/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
        with (temp/"edit-list.csv").open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["part_id","source_in","source_out","cut_at","transition"]); writer.writeheader(); writer.writerows(rows)
        (temp/"README.md").write_text("# 剪映交接包\n\n导入顺序：先导入 `video/` 镜头零件，再导入 `audio/` 音乐；需要时导入 `subtitles/`、`lut/` 和 `storyboard.jpg`，并按 `edit-list.csv` 重建时间线。\n\n本包不是剪映原生草稿，不能直接作为剪映工程打开。\n",encoding="utf-8")
        if dest.exists(): shutil.move(str(dest),str(_archive(dest)))
        os.replace(temp,dest)
    except Exception:
        if temp.exists(): shutil.rmtree(temp)
        raise

def _stage(preview,report,output):
    stage=output.parent/f".{output.name}.delivery-staging-{uuid.uuid4().hex}"; stage.mkdir(parents=True)
    final=stage/"final.mp4"; shutil.copy2(preview,final); final_hash=sha256_file(final)
    if final_hash != sha256_file(preview): raise ValueError("staged final hash does not match preview")
    manifest={"schema":"aerial-delivery-manifest/v1","final_sha256":final_hash,"published_at":datetime.now(timezone.utc).isoformat(),"edit_sha256":report["edit_sha256"],"renderer":report["renderer"],"files":["final.mp4","delivery-manifest.json"]}
    path=stage/"delivery-manifest.json"; write_json_object(path,manifest)
    if load_json_object(path)!=manifest or sha256_file(final)!=manifest["final_sha256"]: raise ValueError("staged delivery manifest verification failed")
    return stage

def _commit(stage,output):
    output.mkdir(parents=True,exist_ok=True); final=output/"final.mp4"; manifest=output/"delivery-manifest.json"; archived_old={}; installed_new=set()
    try:
        for current in (final,manifest):
            if current.exists():
                archive=_archive(current); os.replace(current,archive); archived_old[current]=archive
        os.replace(stage/"final.mp4",final); installed_new.add(final)
        os.replace(stage/"delivery-manifest.json",manifest); installed_new.add(manifest)
    except Exception:
        for current in installed_new:
            if current.exists(): current.unlink()
        for current,archive in reversed(list(archived_old.items())):
            if archive.exists(): os.replace(archive,current)
        raise

def publish(preview_path,report_path,output_dir,*,user_confirmed,jianying=False,library_path=None,edit_path=None,music_path=None,subtitle_path=None,cube_path=None,storyboard_path=None,handoff_dir=None):
    if user_confirmed is not True: raise ValueError("user confirmation required")
    preview=_file(preview_path,"preview"); output=Path(output_dir).resolve(); report=_report(preview,_file(report_path,"edit report"),edit_path)
    handoff=Path(handoff_dir).resolve() if handoff_dir else output.parent/"handoff-jianying"; assets=rows=None
    if jianying:
        if _overlap(output,handoff): raise ValueError("handoff and output paths overlap")
        selected_cube=_approved_cube_for_handoff(edit_path,report,cube_path)
        assets,rows=_handoff_plan(library_path,edit_path,music_path,subtitle_path,selected_cube,storyboard_path)
    stage=None
    try:
        stage=_stage(preview,report,output); _commit(stage,output)
    finally:
        if stage and stage.exists(): shutil.rmtree(stage)
    if jianying: _write_handoff(handoff,assets,rows)
    return output/"final.mp4"

def main():
    p=argparse.ArgumentParser(); p.add_argument("--preview",required=True,type=Path); p.add_argument("--report",required=True,type=Path); p.add_argument("--output-dir",required=True,type=Path); p.add_argument("--user-confirmed",action="store_true"); p.add_argument("--jianying",action="store_true")
    for name in ("library","edit","music","subtitle","cube","storyboard","handoff-dir"): p.add_argument(f"--{name}",type=Path)
    a=p.parse_args(); publish(a.preview,a.report,a.output_dir,user_confirmed=a.user_confirmed,jianying=a.jianying,library_path=a.library,edit_path=a.edit,music_path=a.music,subtitle_path=a.subtitle,cube_path=a.cube,storyboard_path=a.storyboard,handoff_dir=a.handoff_dir)
if __name__ == "__main__": main()
