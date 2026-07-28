/*
 * AP01 AGENTS four-page package loader.
 *
 * Transport and three-slot publication follow the verified loader in
 * /Users/mac/Desktop/cuktech-screen-controller. SHA-256 core adapted for the
 * freestanding target from Brad Conte's public-domain crypto-algorithms.
 */

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long long u64;

#if defined(AP01_CRYPTO_SELF_TEST) || defined(AP01_LOADER_SELF_TEST)
#define ATTR_ENTRY __attribute__((noinline, used))
#else
#define ATTR_ENTRY __attribute__((section(".text.entry"), noinline, used))
#endif
#define ATTR_NOINLINE __attribute__((noinline))

#define VA_STOCK_UI_TIMER                 0xa00bb5dau
#define VA_WINDOW_BY_INDEX                0xa00c5d84u
#define VA_OBJECT_GET_CHILD_COUNT         0xa00c5fe4u
#define VA_LV_GIF_SET_SRC                 0xa00cf8d8u
#define VA_WEBCLIENT_PERFORM              0xa00d86bau
#define VA_OPEN                           0xa003f448u
#define VA_CLOSE                          0xa0026788u
#define VA_READ                           0xa003f5f4u
#define VA_WRITE                          0xa0027d94u
#define VA_MALLOC                         0xa007e1c4u
#define VA_FREE                           0xa007c256u

#define AP01_O_RDONLY                     1
#define AP01_O_RDWR_CREAT_TRUNC           39
#define AP01_MODE_0666                    438

#define ERR_IO                            (-5)
#define ERR_NOMEM                         (-12)
#define ERR_INVAL                         (-22)
#define ERR_FBIG                          (-27)

#define PACKAGE_HEADER_SIZE               256u
#define PACKAGE_HMAC_OFFSET               224u
#define PACKAGE_MAX_BYTES                 (384u * 1024u)
#define PAGE_COUNT                        4u
#define PAGE_MAX_BYTES                    (96u * 1024u)
#define GIF_MIN_BYTES                     13u
#define META_MAGIC                        0x47415041u /* "APAG" */
#define META_SALT                         0x5101a501u
#define META_GENERATION_MASK              0x7fffffffu
#define AGENTS_STATE_MAGIC                0x41504754u
#define WEBCLIENT_SINK_ARG_OFFSET         64u
#define WEBCLIENT_HTTP_STATUS_OFFSET      96u

typedef void (*void_one_arg_fn)(void *);
typedef void *(*window_by_index_fn)(void *, int);
typedef int (*object_get_child_count_fn)(void *);
typedef void (*gif_set_src_fn)(void *, const void *);
typedef int (*webclient_perform_fn)(void *);
typedef int (*open_fn)(const char *, int, int);
typedef int (*close_fn)(int);
typedef int (*io_fn)(int, void *, u32);
typedef int (*write_fn)(int, const void *, u32);
typedef void *(*malloc_fn)(u32);
typedef void (*free_fn)(void *);

extern const u8 agents_device_id[16];
extern const u8 agents_secret_key[32];

struct sha256_context
{
  u8 data[64];
  u32 data_length;
  u32 bit_length_low;
  u32 bit_length_high;
  u32 state[8];
};

struct agents_meta
{
  u32 magic;
  u32 generation;
  u32 slot;
  u32 check;
};

struct agents_ui_state
{
  u32 magic;
  void *gif;
  u32 page;
  u32 applied_generation;
  u32 applied_slot;
  u32 applied_page;
  u32 active;
  void *root;
};

struct download_state
{
  int fd;
  u32 slot;
  u32 total;
  u32 expected_total;
  u32 generation;
  u32 header_length;
  u32 page_index;
  u32 page_written;
  u32 page_length[PAGE_COUNT];
  u32 gif_header_length;
  u32 complete;
  u8 gif_header[10];
  u8 last_byte;
  u8 header[PACKAGE_HEADER_SIZE];
  struct sha256_context page_hash;
  struct sha256_context hmac_inner;
};

typedef char download_state_size_must_be_540[
    sizeof(struct download_state) == 540u ? 1 : -1];

static const char meta_path[] = "/tmp/.ap01a.meta";
static const char ack_path[] = "/tmp/.ap01a.ack";
static const char page00[] = "/tmp/.ap01a00.gif";
static const char page01[] = "/tmp/.ap01a01.gif";
static const char page02[] = "/tmp/.ap01a02.gif";
static const char page03[] = "/tmp/.ap01a03.gif";
static const char page10[] = "/tmp/.ap01a10.gif";
static const char page11[] = "/tmp/.ap01a11.gif";
static const char page12[] = "/tmp/.ap01a12.gif";
static const char page13[] = "/tmp/.ap01a13.gif";
static const char page20[] = "/tmp/.ap01a20.gif";
static const char page21[] = "/tmp/.ap01a21.gif";
static const char page22[] = "/tmp/.ap01a22.gif";
static const char page23[] = "/tmp/.ap01a23.gif";

static const u32 sha256_constants[64] = {
  0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
  0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
  0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
  0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
  0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
  0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
  0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
  0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
  0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
  0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
  0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
  0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
  0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
  0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
  0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
  0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
};

#define ROTRIGHT(value, bits) \
  (((value) >> (bits)) | ((value) << (32u - (bits))))
#define CHOICE(x, y, z) (((x) & (y)) ^ (~(x) & (z)))
#define MAJORITY(x, y, z) (((x) & (y)) ^ ((x) & (z)) ^ ((y) & (z)))
#define EP0(x) (ROTRIGHT((x), 2u) ^ ROTRIGHT((x), 13u) ^ ROTRIGHT((x), 22u))
#define EP1(x) (ROTRIGHT((x), 6u) ^ ROTRIGHT((x), 11u) ^ ROTRIGHT((x), 25u))
#define SIG0(x) (ROTRIGHT((x), 7u) ^ ROTRIGHT((x), 18u) ^ ((x) >> 3u))
#define SIG1(x) (ROTRIGHT((x), 17u) ^ ROTRIGHT((x), 19u) ^ ((x) >> 10u))

static ATTR_NOINLINE void memory_zero(void *target, u32 length)
{
  u8 *bytes = (u8 *)target;
  u32 index;
  for (index = 0u; index < length; ++index)
    {
      bytes[index] = 0u;
    }
}

static int bytes_equal(const u8 *left, const u8 *right, u32 length)
{
  u8 difference = 0u;
  u32 index;
  for (index = 0u; index < length; ++index)
    {
      difference |= left[index] ^ right[index];
    }
  return difference == 0u;
}

static u16 read_u16(const u8 *source)
{
  return (u16)((u16)source[0] | ((u16)source[1] << 8u));
}

static u32 read_u32(const u8 *source)
{
  return (u32)source[0] |
         ((u32)source[1] << 8u) |
         ((u32)source[2] << 16u) |
         ((u32)source[3] << 24u);
}

static ATTR_NOINLINE int fw_open(const char *path, int flags, int mode)
{
#ifdef AP01_LOADER_SELF_TEST
  extern int ap01_selftest_open(const char *, int, int);
  return ap01_selftest_open(path, flags, mode);
#else
  return ((open_fn)VA_OPEN)(path, flags, mode);
#endif
}

static ATTR_NOINLINE int fw_close(int fd)
{
#ifdef AP01_LOADER_SELF_TEST
  extern int ap01_selftest_close(int);
  return ap01_selftest_close(fd);
#else
  return ((close_fn)VA_CLOSE)(fd);
#endif
}

static ATTR_NOINLINE int fw_read(int fd, void *buffer, u32 length)
{
#ifdef AP01_LOADER_SELF_TEST
  extern int ap01_selftest_read(int, void *, u32);
  return ap01_selftest_read(fd, buffer, length);
#else
  return ((io_fn)VA_READ)(fd, buffer, length);
#endif
}

static ATTR_NOINLINE int fw_write(int fd, const void *buffer, u32 length)
{
#ifdef AP01_LOADER_SELF_TEST
  extern int ap01_selftest_write(int, const void *, u32);
  return ap01_selftest_write(fd, buffer, length);
#else
  return ((write_fn)VA_WRITE)(fd, buffer, length);
#endif
}

static ATTR_NOINLINE int write_all(int fd, const void *buffer, u32 length)
{
  const u8 *cursor = (const u8 *)buffer;
  u32 done = 0u;
  while (done < length)
    {
      int amount = fw_write(fd, cursor + done, length - done);
      if (amount <= 0 || (u32)amount > length - done)
        {
          return ERR_IO;
        }
      done += (u32)amount;
    }
  return 0;
}

static ATTR_NOINLINE int read_exact(int fd, void *buffer, u32 length)
{
  u8 *cursor = (u8 *)buffer;
  u32 done = 0u;
  while (done < length)
    {
      int amount = fw_read(fd, cursor + done, length - done);
      if (amount <= 0 || (u32)amount > length - done)
        {
          return ERR_IO;
        }
      done += (u32)amount;
    }
  return 0;
}

static const char *page_path(u32 slot, u32 page)
{
  if (slot == 0u)
    {
      if (page == 0u) return page00;
      if (page == 1u) return page01;
      if (page == 2u) return page02;
      return page03;
    }
  if (slot == 1u)
    {
      if (page == 0u) return page10;
      if (page == 1u) return page11;
      if (page == 2u) return page12;
      return page13;
    }
  if (page == 0u) return page20;
  if (page == 1u) return page21;
  if (page == 2u) return page22;
  return page23;
}

static u32 meta_check(const struct agents_meta *meta)
{
  return meta->magic ^ meta->generation ^ meta->slot ^ META_SALT;
}

static int meta_valid(const struct agents_meta *meta)
{
  return meta->magic == META_MAGIC &&
         meta->generation != 0u &&
         meta->generation <= META_GENERATION_MASK &&
         meta->slot <= 2u &&
         meta->check == meta_check(meta);
}

static int read_record(const char *path, struct agents_meta *meta)
{
  int fd = fw_open(path, AP01_O_RDONLY, 0);
  int result;
  if (fd < 0)
    {
      return ERR_IO;
    }
  result = read_exact(fd, meta, (u32)sizeof(*meta));
  if (fw_close(fd) < 0)
    {
      result = ERR_IO;
    }
  return result < 0 || !meta_valid(meta) ? ERR_INVAL : 0;
}

static int write_record(const char *path, u32 generation, u32 slot)
{
  struct agents_meta meta;
  int fd;
  int result;
  meta.magic = META_MAGIC;
  meta.generation = generation;
  meta.slot = slot;
  meta.check = meta_check(&meta);
  fd = fw_open(path, AP01_O_RDWR_CREAT_TRUNC, AP01_MODE_0666);
  if (fd < 0)
    {
      return ERR_IO;
    }
  result = write_all(fd, &meta, (u32)sizeof(meta));
  if (fw_close(fd) < 0)
    {
      result = ERR_IO;
    }
  return result;
}

static void sha256_transform(struct sha256_context *context, const u8 *data)
{
  u32 words[64];
  u32 a, b, c, d, e, f, g, h, first, second;
  u32 index;
  for (index = 0u; index < 16u; ++index)
    {
      u32 offset = index * 4u;
      words[index] = ((u32)data[offset] << 24u) |
                     ((u32)data[offset + 1u] << 16u) |
                     ((u32)data[offset + 2u] << 8u) |
                     (u32)data[offset + 3u];
    }
  for (; index < 64u; ++index)
    {
      words[index] = SIG1(words[index - 2u]) + words[index - 7u] +
                     SIG0(words[index - 15u]) + words[index - 16u];
    }
  a = context->state[0];
  b = context->state[1];
  c = context->state[2];
  d = context->state[3];
  e = context->state[4];
  f = context->state[5];
  g = context->state[6];
  h = context->state[7];
  for (index = 0u; index < 64u; ++index)
    {
      first = h + EP1(e) + CHOICE(e, f, g) +
              sha256_constants[index] + words[index];
      second = EP0(a) + MAJORITY(a, b, c);
      h = g;
      g = f;
      f = e;
      e = d + first;
      d = c;
      c = b;
      b = a;
      a = first + second;
    }
  context->state[0] += a;
  context->state[1] += b;
  context->state[2] += c;
  context->state[3] += d;
  context->state[4] += e;
  context->state[5] += f;
  context->state[6] += g;
  context->state[7] += h;
}

static void sha256_init(struct sha256_context *context)
{
  context->data_length = 0u;
  context->bit_length_low = 0u;
  context->bit_length_high = 0u;
  context->state[0] = 0x6a09e667u;
  context->state[1] = 0xbb67ae85u;
  context->state[2] = 0x3c6ef372u;
  context->state[3] = 0xa54ff53au;
  context->state[4] = 0x510e527fu;
  context->state[5] = 0x9b05688cu;
  context->state[6] = 0x1f83d9abu;
  context->state[7] = 0x5be0cd19u;
}

static void sha256_update(struct sha256_context *context,
                          const u8 *data, u32 length)
{
  u32 index;
  for (index = 0u; index < length; ++index)
    {
      context->data[context->data_length++] = data[index];
      if (context->data_length == 64u)
        {
          sha256_transform(context, context->data);
          context->bit_length_low += 512u;
          if (context->bit_length_low < 512u)
            {
              context->bit_length_high += 1u;
            }
          context->data_length = 0u;
        }
    }
}

static void sha256_final(struct sha256_context *context, u8 digest[32])
{
  u32 index = context->data_length;
  u32 bit_length_low;
  u32 bit_length_high;
  context->data[index++] = 0x80u;
  if (index > 56u)
    {
      while (index < 64u)
        {
          context->data[index++] = 0u;
        }
      sha256_transform(context, context->data);
      index = 0u;
    }
  while (index < 56u)
    {
      context->data[index++] = 0u;
    }
  bit_length_low = context->bit_length_low + context->data_length * 8u;
  bit_length_high = context->bit_length_high;
  if (bit_length_low < context->bit_length_low)
    {
      bit_length_high += 1u;
    }
  context->data[56] = (u8)(bit_length_high >> 24u);
  context->data[57] = (u8)(bit_length_high >> 16u);
  context->data[58] = (u8)(bit_length_high >> 8u);
  context->data[59] = (u8)bit_length_high;
  context->data[60] = (u8)(bit_length_low >> 24u);
  context->data[61] = (u8)(bit_length_low >> 16u);
  context->data[62] = (u8)(bit_length_low >> 8u);
  context->data[63] = (u8)bit_length_low;
  sha256_transform(context, context->data);
  for (index = 0u; index < 4u; ++index)
    {
      digest[index] = (u8)(context->state[0] >> (24u - index * 8u));
      digest[index + 4u] = (u8)(context->state[1] >> (24u - index * 8u));
      digest[index + 8u] = (u8)(context->state[2] >> (24u - index * 8u));
      digest[index + 12u] = (u8)(context->state[3] >> (24u - index * 8u));
      digest[index + 16u] = (u8)(context->state[4] >> (24u - index * 8u));
      digest[index + 20u] = (u8)(context->state[5] >> (24u - index * 8u));
      digest[index + 24u] = (u8)(context->state[6] >> (24u - index * 8u));
      digest[index + 28u] = (u8)(context->state[7] >> (24u - index * 8u));
    }
}

static void hmac_init(struct sha256_context *inner)
{
  u8 pad[64];
  u32 index;
  for (index = 0u; index < 64u; ++index)
    {
      pad[index] = (index < 32u ? agents_secret_key[index] : 0u) ^ 0x36u;
    }
  sha256_init(inner);
  sha256_update(inner, pad, 64u);
}

static void hmac_final(struct sha256_context *inner, u8 digest[32])
{
  struct sha256_context outer;
  u8 inner_digest[32];
  u8 pad[64];
  u32 index;
  sha256_final(inner, inner_digest);
  for (index = 0u; index < 64u; ++index)
    {
      pad[index] = (index < 32u ? agents_secret_key[index] : 0u) ^ 0x5cu;
    }
  sha256_init(&outer);
  sha256_update(&outer, pad, 64u);
  sha256_update(&outer, inner_digest, 32u);
  sha256_final(&outer, digest);
}

#ifdef AP01_CRYPTO_SELF_TEST
int ap01_agents_crypto_self_test(const u8 *data, u32 length, u8 digest[32])
{
  struct sha256_context inner;
  hmac_init(&inner);
  sha256_update(&inner, data, length);
  hmac_final(&inner, digest);
  return 0;
}
#endif

static int gif_header_valid(const u8 *header)
{
  return header[0] == (u8)'G' && header[1] == (u8)'I' &&
         header[2] == (u8)'F' && header[3] == (u8)'8' &&
         header[4] == (u8)'9' && header[5] == (u8)'a' &&
         header[6] == 0x40u && header[7] == 0x01u &&
         header[8] == 0xf0u && header[9] == 0x00u;
}

static int validate_package_header(struct download_state *state)
{
  u32 index;
  u32 body_total = 0u;
  if (state->header[0] != (u8)'A' || state->header[1] != (u8)'P' ||
      state->header[2] != (u8)'A' || state->header[3] != (u8)'G' ||
      read_u16(state->header + 4u) != 1u ||
      read_u16(state->header + 6u) != PACKAGE_HEADER_SIZE ||
      read_u32(state->header + 24u) != PAGE_COUNT ||
      read_u32(state->header + 28u) != 0u ||
      !bytes_equal(state->header + 176u, agents_device_id, 16u))
    {
      return ERR_INVAL;
    }
  for (index = 192u; index < PACKAGE_HMAC_OFFSET; ++index)
    {
      if (state->header[index] != 0u)
        {
          return ERR_INVAL;
        }
    }
  state->generation = read_u32(state->header + 8u);
  state->expected_total = read_u32(state->header + 12u);
  if (state->generation == 0u ||
      state->generation > META_GENERATION_MASK ||
      state->expected_total < PACKAGE_HEADER_SIZE ||
      state->expected_total > PACKAGE_MAX_BYTES)
    {
      return ERR_FBIG;
    }
  for (index = 0u; index < PAGE_COUNT; ++index)
    {
      state->page_length[index] = read_u32(state->header + 32u + index * 4u);
      if (state->page_length[index] < GIF_MIN_BYTES ||
          state->page_length[index] > PAGE_MAX_BYTES ||
          body_total > PACKAGE_MAX_BYTES - state->page_length[index])
        {
          return ERR_FBIG;
        }
      body_total += state->page_length[index];
    }
  if (body_total != state->expected_total - PACKAGE_HEADER_SIZE)
    {
      return ERR_INVAL;
    }
  hmac_init(&state->hmac_inner);
  sha256_update(&state->hmac_inner, state->header, PACKAGE_HMAC_OFFSET);
  return 0;
}

static int open_current_page(struct download_state *state)
{
  state->fd = fw_open(
      page_path(state->slot, state->page_index),
      AP01_O_RDWR_CREAT_TRUNC,
      AP01_MODE_0666);
  if (state->fd < 0)
    {
      return ERR_IO;
    }
  state->page_written = 0u;
  state->gif_header_length = 0u;
  state->last_byte = 0u;
  sha256_init(&state->page_hash);
  return 0;
}

static int finish_current_page(struct download_state *state)
{
  u8 digest[32];
  int close_result = fw_close(state->fd);
  state->fd = -1;
  sha256_final(&state->page_hash, digest);
  if (close_result < 0 ||
      state->page_written != state->page_length[state->page_index] ||
      state->gif_header_length != 10u ||
      !gif_header_valid(state->gif_header) ||
      state->last_byte != 0x3bu ||
      !bytes_equal(
          digest,
          state->header + 48u + state->page_index * 32u,
          32u))
    {
      return ERR_INVAL;
    }
  state->page_index += 1u;
  if (state->page_index == PAGE_COUNT)
    {
      state->complete = 1u;
      return 0;
    }
  return open_current_page(state);
}

static int consume_body(struct download_state *state,
                        const u8 *data, u32 length)
{
  u32 offset = 0u;
  if (state->page_index >= PAGE_COUNT)
    {
      return ERR_FBIG;
    }
  if (state->fd < 0 && open_current_page(state) < 0)
    {
      return ERR_IO;
    }
  while (offset < length)
    {
      u32 remaining = state->page_length[state->page_index] -
                      state->page_written;
      u32 amount = length - offset < remaining ? length - offset : remaining;
      u32 header_index = 0u;
      while (state->gif_header_length < 10u && header_index < amount)
        {
          state->gif_header[state->gif_header_length++] =
              data[offset + header_index++];
        }
      sha256_update(&state->page_hash, data + offset, amount);
      sha256_update(&state->hmac_inner, data + offset, amount);
      if (write_all(state->fd, data + offset, amount) < 0)
        {
          return ERR_IO;
        }
      state->page_written += amount;
      state->last_byte = data[offset + amount - 1u];
      offset += amount;
      if (state->page_written == state->page_length[state->page_index] &&
          finish_current_page(state) < 0)
        {
          return ERR_INVAL;
        }
      if (state->complete != 0u && offset < length)
        {
          return ERR_FBIG;
        }
    }
  return 0;
}

ATTR_ENTRY int ap01_agents_sink(char **buffer, int offset, int data_end,
                                int *buffer_length, void *argument)
{
  struct download_state *state = (struct download_state *)argument;
  const u8 *chunk;
  u32 length;
  u32 consumed = 0u;
  if (state == (void *)0 || buffer == (void *)0 ||
      *buffer == (void *)0 || buffer_length == (void *)0 ||
      offset < 0 || data_end < offset || *buffer_length < 0 ||
      data_end > *buffer_length)
    {
      return ERR_INVAL;
    }
  length = (u32)(data_end - offset);
  if (length == 0u)
    {
      return 0;
    }
  if (length > PACKAGE_MAX_BYTES ||
      state->total > PACKAGE_MAX_BYTES - length)
    {
      return ERR_FBIG;
    }
  chunk = (const u8 *)(*buffer) + (u32)offset;
  while (state->header_length < PACKAGE_HEADER_SIZE && consumed < length)
    {
      state->header[state->header_length++] = chunk[consumed++];
    }
  if (state->header_length == PACKAGE_HEADER_SIZE &&
      state->expected_total == 0u &&
      validate_package_header(state) < 0)
    {
      return ERR_INVAL;
    }
  if (consumed < length &&
      consume_body(state, chunk + consumed, length - consumed) < 0)
    {
      return ERR_INVAL;
    }
  state->total += length;
  if (state->expected_total != 0u && state->total > state->expected_total)
    {
      return ERR_FBIG;
    }
  return 0;
}

ATTR_ENTRY int ap01_agents_webclient_wrapper(void *context)
{
  struct agents_meta old_meta;
  struct agents_meta old_ack;
  struct download_state *state;
  u32 next_slot;
  u32 have_meta;
  u32 have_ack;
  int result;
  int close_result = 0;
  u8 actual_hmac[32];
  if (context == (void *)0)
    {
      return ERR_INVAL;
    }
  state = (struct download_state *)((malloc_fn)VA_MALLOC)(
      (u32)sizeof(struct download_state));
  if (state == (void *)0)
    {
      return ERR_NOMEM;
    }
  memory_zero(state, (u32)sizeof(*state));
  state->fd = -1;
  have_meta = read_record(meta_path, &old_meta) == 0 ? 1u : 0u;
  have_ack = read_record(ack_path, &old_ack) == 0 ? 1u : 0u;
  for (next_slot = 0u; next_slot < 3u; ++next_slot)
    {
      if ((have_meta == 0u || next_slot != old_meta.slot) &&
          (have_ack == 0u || next_slot != old_ack.slot))
        {
          break;
        }
    }
  if (next_slot >= 3u)
    {
      ((free_fn)VA_FREE)(state);
      return ERR_IO;
    }
  state->slot = next_slot;
  *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = state;
  result = ((webclient_perform_fn)VA_WEBCLIENT_PERFORM)(context);
  *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = (void *)0;
  if (state->fd >= 0)
    {
      close_result = fw_close(state->fd);
      state->fd = -1;
    }
  if (result >= 0 &&
      *(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) == 200u &&
      close_result >= 0 &&
      state->complete != 0u &&
      state->total == state->expected_total)
    {
      hmac_final(&state->hmac_inner, actual_hmac);
      if (!bytes_equal(
              actual_hmac,
              state->header + PACKAGE_HMAC_OFFSET,
              32u) ||
          write_record(meta_path, state->generation, state->slot) < 0)
        {
          result = ERR_INVAL;
        }
    }
  else if (result >= 0)
    {
      result = ERR_INVAL;
    }
  ((free_fn)VA_FREE)(state);
  return result;
}

ATTR_ENTRY int ap01_agents_apply_current(void *argument)
{
  struct agents_ui_state *state = (struct agents_ui_state *)argument;
  struct agents_meta meta;
  if (state == (void *)0 || state->magic != AGENTS_STATE_MAGIC ||
      state->gif == (void *)0 || state->page >= PAGE_COUNT ||
      read_record(meta_path, &meta) < 0)
    {
      return 0;
    }
  if (state->applied_generation == meta.generation &&
      state->applied_slot == meta.slot &&
      state->applied_page == state->page)
    {
      return 1;
    }
  ((gif_set_src_fn)VA_LV_GIF_SET_SRC)(
      state->gif,
      page_path(meta.slot, state->page));
  if (*(void **)((u8 *)state->gif + 0x5cu) == (void *)0)
    {
      return 0;
    }
  state->applied_generation = meta.generation;
  state->applied_slot = meta.slot;
  state->applied_page = state->page;
  (void)write_record(ack_path, meta.generation, meta.slot);
  return 1;
}

ATTR_ENTRY void ap01_agents_ui_timer_wrapper(void *timer)
{
  void *theme;
  void *pet;
  void *root;
  struct agents_ui_state *state;
  int count;
  int index;
  ((void_one_arg_fn)VA_STOCK_UI_TIMER)(timer);
  if (timer == (void *)0)
    {
      return;
    }
  theme = *(void **)((u8 *)timer + 12u);
  if (theme == (void *)0)
    {
      return;
    }
  pet = ((window_by_index_fn)VA_WINDOW_BY_INDEX)(theme, 7);
  if (pet == (void *)0)
    {
      return;
    }
  count = ((object_get_child_count_fn)VA_OBJECT_GET_CHILD_COUNT)(pet);
  for (index = count - 1; index >= 0; --index)
    {
      root = ((window_by_index_fn)VA_WINDOW_BY_INDEX)(pet, index);
      if (root == (void *)0)
        {
          continue;
        }
      state = (struct agents_ui_state *)*(void **)((u8 *)root + 16u);
      if (state != (void *)0 &&
          state->magic == AGENTS_STATE_MAGIC &&
          state->gif != (void *)0 &&
          state->root == root)
        {
          (void)ap01_agents_apply_current(state);
          return;
        }
    }
}
