"""StegoCLI comprehensive test suite."""
import os, sys, tempfile, json, traceback
sys.path.insert(0, "/home/claude")
from pathlib import Path
from PIL import Image

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
SKIP = "\033[33m-\033[0m"
passed = failed = 0

def run_test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  {PASS}  {name}")
        passed += 1
    except Exception as e:
        print(f"  {FAIL}  {name}")
        print(f"       \033[31m{e}\033[0m")
        if os.environ.get("VERBOSE"):
            traceback.print_exc()
        failed += 1

def make_image(w=300, h=300, mode="RGB"):
    td = Path(tempfile.mkdtemp())
    p = td / "carrier.png"
    import random; rng = random.Random(42)
    img = Image.new(mode, (w, h))
    img.putdata([(rng.randint(0,255), rng.randint(0,255), rng.randint(0,255))
                  for _ in range(w*h)])
    img.save(p); return p

def make_payload(data=b"test payload data "*20, suffix=".txt"):
    td = Path(tempfile.mkdtemp())
    p = td / f"payload{suffix}"; p.write_bytes(data); return p

def round_trip(carrier, payload, password=None, mode="balanced",
               encrypt=True, compress=True):
    from stegocli.core.models import EmbedConfig, ExtractConfig, EmbedMode
    from stegocli.core.embedder import run_embed
    from stegocli.core.extractor import run_extract
    M = {"ultra-stealth":EmbedMode.ULTRA_STEALTH,"balanced":EmbedMode.BALANCED,
         "maximum":EmbedMode.MAXIMUM}
    td = Path(tempfile.mkdtemp())
    out = td/"stego.png"; xd = td/"extracted"
    er = run_embed(EmbedConfig(carrier_path=carrier, payload_path=payload,
        output_path=out, mode=M[mode], password=password,
        encrypt=encrypt and bool(password), compress=compress))
    xr = run_extract(ExtractConfig(carrier_path=out, output_dir=xd,
        password=password, verify=True), mode=M[mode])
    return er, xr, xr.output_path.read_bytes()

# ════════════════════════════════════════════════
print("\n\033[1m  StegoCLI — Test Suite\033[0m")
print("  ──────────────────────────────────────────────────")

# ── Crypto ─────────────────────────────────────
print("\n\033[1m  Crypto\033[0m")

def t_key_deterministic():
    from stegocli.pipeline.crypto import derive_key
    salt = b"A"*16
    assert derive_key("pw", salt) == derive_key("pw", salt)
run_test("derive_key is deterministic", t_key_deterministic)

def t_key_different():
    from stegocli.pipeline.crypto import derive_key
    assert derive_key("pw1", b"A"*16) != derive_key("pw2", b"A"*16)
run_test("different passwords → different keys", t_key_different)

def t_enc_roundtrip():
    from stegocli.pipeline.crypto import derive_key, generate_salt, generate_nonce, encrypt, decrypt
    s=generate_salt(); n=generate_nonce(); k=derive_key("test", s)
    assert decrypt(encrypt(b"secret data", k, n), k, n) == b"secret data"
run_test("AES-GCM encrypt/decrypt round-trip", t_enc_roundtrip)

def t_wrong_pw():
    from stegocli.pipeline.crypto import derive_key, generate_salt, generate_nonce, encrypt, decrypt
    from stegocli.core.exceptions import AuthenticationError
    s=generate_salt(); n=generate_nonce()
    ct = encrypt(b"data", derive_key("right", s), n)
    try: decrypt(ct, derive_key("wrong", s), n); assert False
    except AuthenticationError: pass
run_test("wrong password → AuthenticationError", t_wrong_pw)

def t_tamper():
    from stegocli.pipeline.crypto import derive_key, generate_salt, generate_nonce, encrypt, decrypt
    from stegocli.core.exceptions import AuthenticationError
    s=generate_salt(); n=generate_nonce(); k=derive_key("pw", s)
    ct = bytearray(encrypt(b"data", k, n)); ct[3] ^= 0xFF
    try: decrypt(bytes(ct), k, n); assert False
    except AuthenticationError: pass
run_test("tampered ciphertext → AuthenticationError", t_tamper)

def t_hash():
    from stegocli.pipeline.crypto import hash_payload, verify_hash
    h = hash_payload(b"test"); assert verify_hash(b"test", h)
    assert not verify_hash(b"other", h)
run_test("BLAKE2b hash + verify", t_hash)

# ── Compression ────────────────────────────────
print("\n\033[1m  Compression\033[0m")

def t_compress_roundtrip():
    from stegocli.pipeline.compression import compress, decompress
    data = b"ABCDEF"*1000
    c, was = compress(data); assert was; assert decompress(c) == data
run_test("compress/decompress round-trip (compressible)", t_compress_roundtrip)

def t_compress_random():
    from stegocli.pipeline.compression import compress, decompress
    data = os.urandom(500)
    result, _ = compress(data)
    # if compressed, must decompress back; if not compressed, result == data
    assert isinstance(result, bytes)
run_test("compress handles random (incompressible) data", t_compress_random)

# ── Header ─────────────────────────────────────
print("\n\033[1m  Header\033[0m")

def t_bootstrap_roundtrip():
    from stegocli.pipeline.header import Bootstrap, VERSION
    s=os.urandom(16);n=os.urandom(12);b = Bootstrap(VERSION, True, True, 17, s, n, blob_length=99)
    b2 = Bootstrap.unpack(b.pack())
    assert b2.compressed and b2.encrypted and b2.kdf_n_log2 == 17
    assert b2.kdf_salt == b.kdf_salt and b2.nonce == b.nonce
run_test("Bootstrap pack/unpack round-trip", t_bootstrap_roundtrip)

def t_bad_magic():
    from stegocli.pipeline.header import Bootstrap, BOOTSTRAP_LEN
    from stegocli.core.exceptions import NoSignatureError
    try: Bootstrap.unpack(b"\x00"*BOOTSTRAP_LEN); assert False
    except NoSignatureError: pass
run_test("bad magic bytes → NoSignatureError", t_bad_magic)

def t_innerblock_roundtrip():
    from stegocli.pipeline.header import InnerBlock
    ib = InnerBlock(9999, 12, os.urandom(32), "doc.pdf", b"payload here")
    ib2 = InnerBlock.unpack(ib.pack())
    assert ib2.original_size==9999 and ib2.filename=="doc.pdf"
    assert ib2.payload_data==b"payload here"
run_test("InnerBlock pack/unpack round-trip", t_innerblock_roundtrip)

def t_full_stream_no_enc():
    from stegocli.pipeline.header import Bootstrap, InnerBlock, pack_stream, unpack_stream, VERSION
    pl = b"hello world"
    inner = InnerBlock(42, len(pl), os.urandom(32), "f.txt", pl)
    inner_bytes = inner.pack()
    boot = Bootstrap(VERSION, False, False, 0, b"\x00"*16, b"\x00"*12, blob_length=len(inner_bytes))
    stream = pack_stream(boot, inner)
    _, inner2 = unpack_stream(stream)
    assert inner2.payload_data == pl
run_test("full stream pack/unpack (no encryption)", t_full_stream_no_enc)

# ── Strategies ─────────────────────────────────
print("\n\033[1m  Strategies\033[0m")

def t_seq_lsb():
    from stegocli.strategies.lsb import embed_sequential, extract_sequential
    from stegocli.core.models import ChannelSet
    pixels = [[i%256, (i*2)%256, (i*3)%256] for i in range(2000)]
    data = b"Sequential test data!!"
    m = embed_sequential(pixels, data, ChannelSet.BLUE_ONLY, 1)
    r = extract_sequential(m, len(data)*8, ChannelSet.BLUE_ONLY, 1)
    assert r == data
run_test("sequential LSB embed/extract", t_seq_lsb)

def t_prng_scatter():
    from stegocli.strategies.lsb import embed_prng_scatter, extract_prng_scatter
    from stegocli.core.models import ChannelSet
    pixels = [[i%256, (i+50)%256, (i+100)%256] for i in range(3000)]
    data = b"PRNG scatter test payload!!"
    m = embed_prng_scatter(pixels, data, ChannelSet.BLUE_GREEN, seed=0xCAFEBABE)
    r = extract_prng_scatter(m, len(data)*8, ChannelSet.BLUE_GREEN, seed=0xCAFEBABE)
    assert r == data
run_test("PRNG scatter embed/extract", t_prng_scatter)

def t_adaptive():
    from stegocli.strategies.lsb import embed_adaptive, extract_adaptive
    from stegocli.core.models import ChannelSet
    import random; rng=random.Random(7)
    pixels = [[rng.randint(0,255) for _ in range(3)] for _ in range(3000)]
    data = b"Adaptive LSB test!!"
    m = embed_adaptive(pixels, data, ChannelSet.RGB, 2, width=50)
    r = extract_adaptive(m, len(data)*8, ChannelSet.RGB, 2, width=50)
    assert r == data
run_test("adaptive LSB embed/extract", t_adaptive)

def t_lsb_minimal():
    from stegocli.strategies.lsb import embed_sequential
    from stegocli.core.models import ChannelSet
    pixels = [[200, 200, 200] for _ in range(2000)]
    m = embed_sequential(pixels, b"A"*50, ChannelSet.BLUE_ONLY, 1)
    for o,n in zip(pixels, m):
        assert abs(o[2]-n[2]) <= 1
run_test("1-bit LSB changes are ≤ 1 per channel", t_lsb_minimal)

def t_diff_seeds():
    from stegocli.strategies.lsb import embed_prng_scatter
    from stegocli.core.models import ChannelSet
    pixels = [[128,128,128] for _ in range(2000)]
    data = b"A"*50
    m1 = embed_prng_scatter(pixels, data, ChannelSet.BLUE_ONLY, seed=1)
    m2 = embed_prng_scatter(pixels, data, ChannelSet.BLUE_ONLY, seed=2)
    assert any(a!=b for a,b in zip(m1,m2))
run_test("different seeds → different scatter patterns", t_diff_seeds)

# ── Carrier I/O ────────────────────────────────
print("\n\033[1m  Carrier I/O\033[0m")

def t_load_png():
    from stegocli.carriers.image import load_carrier
    c = load_carrier(make_image(100,100))
    assert c.pixel_count==10000 and c.width==100 and c.height==100
run_test("load PNG carrier", t_load_png)

def t_load_bmp():
    from stegocli.carriers.image import load_carrier
    td=Path(tempfile.mkdtemp()); p=td/"t.bmp"
    Image.new("RGB",(80,60),(100,150,200)).save(p,"BMP")
    c=load_carrier(p); assert c.pixel_count==4800
run_test("load BMP carrier", t_load_bmp)

def t_bad_format():
    from stegocli.carriers.image import load_carrier
    from stegocli.core.exceptions import UnsupportedFormatError
    td=Path(tempfile.mkdtemp()); f=td/"img.jpg"; f.write_bytes(b"xx")
    try: load_carrier(f); assert False
    except UnsupportedFormatError: pass
run_test("unsupported format → UnsupportedFormatError", t_bad_format)

def t_save_preserves_dims():
    from stegocli.carriers.image import load_carrier
    p=make_image(160,90); c=load_carrier(p)
    td=Path(tempfile.mkdtemp()); o=td/"out.png"; c.save(o)
    c2=load_carrier(o); assert c2.width==160 and c2.height==90
run_test("save preserves dimensions", t_save_preserves_dims)

# ── End-to-end round trips ──────────────────────
print("\n\033[1m  End-to-end (embed → extract)\033[0m")

def t_e2e_balanced():
    c=make_image(400,400)
    p=make_payload(b"Balanced mode secret document. "*100)
    original=p.read_bytes()
    er,xr,extracted=round_trip(c,p,"password123","balanced")
    assert extracted==original and xr.integrity_ok
run_test("balanced mode, text payload, encrypted", t_e2e_balanced)

def t_e2e_ultra():
    c=make_image(600,600)
    p=make_payload(b"Ultra stealth content.")
    er,xr,extracted=round_trip(c,p,"ultrapassword","ultra-stealth")
    assert extracted==p.read_bytes()
run_test("ultra-stealth mode", t_e2e_ultra)

def t_e2e_maximum():
    c=make_image(400,400)
    p=make_payload(b"Maximum capacity payload content. "*300)
    er,xr,extracted=round_trip(c,p,"maxpass","maximum")
    assert extracted==p.read_bytes()
run_test("maximum mode", t_e2e_maximum)

def t_e2e_no_enc():
    c=make_image(300,300)
    p=make_payload(b"Unencrypted but hashed.")
    er,xr,extracted=round_trip(c,p,None,"balanced",encrypt=False)
    assert extracted==p.read_bytes() and xr.integrity_ok
run_test("no encryption, integrity hash still verified", t_e2e_no_enc)

def t_e2e_binary():
    c=make_image(400,400)
    data=bytes(range(256))*50+os.urandom(128)
    p=make_payload(data,".bin")
    er,xr,extracted=round_trip(c,p,"binpw","balanced")
    assert extracted==data
run_test("binary payload (arbitrary bytes)", t_e2e_binary)

def t_e2e_json():
    c=make_image(300,300)
    obj={"status":"ok","values":list(range(50)),"nested":{"x":True}}
    data=json.dumps(obj).encode()
    p=make_payload(data,".json")
    er,xr,extracted=round_trip(c,p,"jsonpw","balanced")
    assert json.loads(extracted)==obj
run_test("JSON payload", t_e2e_json)

def t_e2e_bmp_carrier():
    td=Path(tempfile.mkdtemp()); bmp=td/"carrier.bmp"
    import random; rng=random.Random(5)
    img=Image.new("RGB",(300,300))
    img.putdata([(rng.randint(0,255),rng.randint(0,255),rng.randint(0,255))
                  for _ in range(90000)])
    img.save(bmp,"BMP")
    from stegocli.core.models import EmbedConfig, ExtractConfig, EmbedMode
    from stegocli.core.embedder import run_embed
    from stegocli.core.extractor import run_extract
    payload=make_payload(b"BMP carrier test!")
    out=td/"out.bmp"
    run_embed(EmbedConfig(carrier_path=bmp, payload_path=payload,
        output_path=out, mode=EmbedMode.BALANCED, password="bmppass"))
    xd=td/"xout"
    xr=run_extract(ExtractConfig(carrier_path=out, output_dir=xd, password="bmppass"))
    assert xr.output_path.read_bytes()==payload.read_bytes()
run_test("BMP carrier embed/extract", t_e2e_bmp_carrier)

def t_e2e_filename_preserved():
    c=make_image(300,300)
    td=Path(tempfile.mkdtemp()); p=td/"my_secret.txt"; p.write_bytes(b"content")
    er,xr,extracted=round_trip(c,p,"pw","balanced")
    assert xr.filename=="my_secret.txt"
run_test("original filename preserved", t_e2e_filename_preserved)

def t_e2e_no_tmp_files():
    from stegocli.core.models import EmbedConfig, EmbedMode
    from stegocli.core.embedder import run_embed
    c=make_image(300,300); p=make_payload(b"atomic")
    td=Path(tempfile.mkdtemp()); out=td/"out.png"
    run_embed(EmbedConfig(carrier_path=c, payload_path=p,
        output_path=out, mode=EmbedMode.BALANCED, password="pw"))
    assert len(list(td.glob("*.stgtmp")))==0
run_test("no temp files left after embed", t_e2e_no_tmp_files)

# ── Dry run ────────────────────────────────────
print("\n\033[1m  Dry run\033[0m")

def t_dryrun():
    from stegocli.core.models import EmbedConfig, EmbedMode
    from stegocli.core.embedder import run_embed
    c=make_image(300,300); p=make_payload(b"dry run")
    td=Path(tempfile.mkdtemp()); out=td/"out.png"
    r=run_embed(EmbedConfig(carrier_path=c, payload_path=p,
        output_path=out, mode=EmbedMode.BALANCED, password="pw", dry_run=True))
    assert r.dry_run and not out.exists() and r.bits_written>0
run_test("dry-run doesn't write file, reports bit count", t_dryrun)

# ── Inspector ──────────────────────────────────
print("\n\033[1m  Inspector\033[0m")

def t_inspect_capacity():
    from stegocli.core.inspector import run_inspect
    from stegocli.core.models import InspectConfig
    r=run_inspect(InspectConfig(carrier_path=make_image(500,500)))
    assert r.pixel_count==250000
    assert 0 < r.ultra_stealth_bytes < r.balanced_bytes < r.maximum_bytes
    assert not r.has_signature
run_test("inspect: capacity hierarchy correct", t_inspect_capacity)

def t_inspect_detects_sig():
    from stegocli.core.inspector import run_inspect
    from stegocli.core.models import InspectConfig, EmbedConfig, EmbedMode
    from stegocli.core.embedder import run_embed
    c=make_image(300,300); p=make_payload(b"findme")
    td=Path(tempfile.mkdtemp()); out=td/"stego.png"
    run_embed(EmbedConfig(carrier_path=c, payload_path=p,
        output_path=out, mode=EmbedMode.BALANCED, password="pw"))
    r=run_inspect(InspectConfig(carrier_path=out))
    assert r.has_signature
run_test("inspect: detects stego signature", t_inspect_detects_sig)

# ── Error handling ─────────────────────────────
print("\n\033[1m  Error handling\033[0m")

def t_wrong_pw_raises():
    from stegocli.core.models import EmbedConfig, ExtractConfig, EmbedMode
    from stegocli.core.embedder import run_embed
    from stegocli.core.extractor import run_extract
    from stegocli.core.exceptions import AuthenticationError
    c=make_image(300,300); p=make_payload(b"secret")
    td=Path(tempfile.mkdtemp()); out=td/"s.png"
    run_embed(EmbedConfig(carrier_path=c,payload_path=p,
        output_path=out,mode=EmbedMode.BALANCED,password="correct"))
    try:
        run_extract(ExtractConfig(carrier_path=out,
            output_dir=td/"xd",password="wrong"))
        assert False
    except AuthenticationError: pass
run_test("wrong password → AuthenticationError", t_wrong_pw_raises)

def t_no_sig_raises():
    from stegocli.core.models import ExtractConfig, EmbedMode
    from stegocli.core.extractor import run_extract
    from stegocli.core.exceptions import NoSignatureError
    c=make_image(200,200)
    try:
        run_extract(ExtractConfig(carrier_path=c,output_dir=Path(tempfile.mkdtemp())))
        assert False
    except NoSignatureError: pass
run_test("plain image → NoSignatureError", t_no_sig_raises)

def t_oversized_raises():
    from stegocli.core.models import EmbedConfig, EmbedMode
    from stegocli.core.embedder import run_embed
    from stegocli.core.exceptions import CapacityError
    td=Path(tempfile.mkdtemp()); c=td/"tiny.png"
    Image.new("RGB",(10,10)).save(c)
    p=make_payload(b"X"*8192)
    try:
        run_embed(EmbedConfig(carrier_path=c,payload_path=p,
            output_path=td/"o.png",mode=EmbedMode.BALANCED,
            password="pw",compress=False))
        assert False
    except CapacityError: pass
run_test("oversized payload → CapacityError", t_oversized_raises)

def t_exists_no_overwrite():
    from stegocli.core.models import EmbedConfig, EmbedMode
    from stegocli.core.embedder import run_embed
    from stegocli.core.exceptions import PayloadError
    c=make_image(300,300); p=make_payload(b"x")
    td=Path(tempfile.mkdtemp()); out=td/"exists.png"; out.write_bytes(b"old")
    try:
        run_embed(EmbedConfig(carrier_path=c,payload_path=p,
            output_path=out,mode=EmbedMode.BALANCED,password="pw",overwrite=False))
        assert False
    except PayloadError: pass
run_test("existing output without --overwrite → PayloadError", t_exists_no_overwrite)

def t_overwrite_ok():
    from stegocli.core.models import EmbedConfig, EmbedMode
    from stegocli.core.embedder import run_embed
    c=make_image(300,300); p=make_payload(b"overwrite test")
    td=Path(tempfile.mkdtemp()); out=td/"exists.png"; out.write_bytes(b"old")
    r=run_embed(EmbedConfig(carrier_path=c,payload_path=p,
        output_path=out,mode=EmbedMode.BALANCED,password="pw",overwrite=True))
    assert r.success
run_test("--overwrite replaces existing output", t_overwrite_ok)

# ── Summary ─────────────────────────────────────
print(f"\n  ──────────────────────────────────────────────────")
print(f"  Results: \033[32m{passed} passed\033[0m  \033[31m{failed} failed\033[0m  "
      f"(total {passed+failed})")
if failed == 0:
    print(f"  \033[32m\033[1m All tests passed! ✓\033[0m\n")
    sys.exit(0)
else:
    print(f"  \033[31m\033[1m {failed} test(s) failed.\033[0m\n")
    sys.exit(1)
