/*
 * AP01 AGENTS four-page package loader.
 *
 * Transport and three-slot publication follow the verified loader in
 * /Users/mac/Desktop/cuktech-screen-controller.
 */

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long long u64;

#if defined(AP01_CRC_SELF_TEST) || defined(AP01_LOADER_SELF_TEST)
#define ATTR_ENTRY __attribute__((noinline, used))
#else
#define ATTR_ENTRY __attribute__((section(".text.entry"), noinline, used))
#endif
#define ATTR_NOINLINE __attribute__((noinline))

#define VA_STOCK_UI_TIMER                 0xa00bb5dau
#define VA_STOCK_GET_DISPATCH             0xa00be388u
#define VA_STOCK_GET_CHILD                0xa00be3cau
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
#define ERR_INVAL                         (-22)
#define ERR_FBIG                          (-27)

#define PACKAGE_HEADER_SIZE               64u
#define PACKAGE_MAX_BYTES                 (384u * 1024u)
#define PAGE_COUNT                        4u
#define PAGE_MAX_BYTES                    (96u * 1024u)
#define GIF_MIN_BYTES                     13u
#define META_MAGIC                        0x47415041u /* "APAG" */
#define META_SALT                         0x5101a501u
#define META_GENERATION_MASK              0x7fffffffu
#define AGENTS_TAIL_MAGIC                 0xa5010000u
#define AGENTS_TAIL_MAGIC_MASK            0xffff0000u
#define AGENTS_STATE_CLOSED               0u
#define AGENTS_STATE_OVERVIEW             1u
#define AGENTS_STATE_LAST_30_DAYS         4u
#define WEBCLIENT_SINK_ARG_OFFSET         64u
#define WEBCLIENT_HTTP_STATUS_OFFSET      96u

typedef void (*void_one_arg_fn)(void *);
typedef int (*stock_get_dispatch_fn)(void *);
typedef void *(*stock_get_child_fn)(void *, int);
typedef void (*gif_set_src_fn)(void *, const void *);
typedef int (*webclient_perform_fn)(void *);
typedef int (*open_fn)(const char *, int, int);
typedef int (*close_fn)(int);
typedef int (*io_fn)(int, void *, u32);
typedef int (*write_fn)(int, const void *, u32);
typedef void *(*malloc_fn)(u32);
typedef void (*free_fn)(void *);

struct agents_meta
{
  u32 magic;
  u32 generation;
  u32 slot;
  u32 check;
};

struct stock_pet_state
{
  void *gif;
  u32 stock_field_4;
  u32 stock_field_8;
  u32 stock_field_12;
  u32 agents_state;
};

extern int ap01_agents_restore_pet(void *);

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
  u32 page_crc;
};

typedef char download_state_size_must_be_136[
    sizeof(struct download_state) == 136u ? 1 : -1];

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

static ATTR_NOINLINE void memory_zero(void *target, u32 length)
{
  u8 *bytes = (u8 *)target;
  u32 index;
  for (index = 0u; index < length; ++index)
    {
      bytes[index] = 0u;
    }
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

static int agents_state_decode(u32 encoded, u32 *state)
{
  u32 value;
  if ((encoded & AGENTS_TAIL_MAGIC_MASK) != AGENTS_TAIL_MAGIC)
    {
      return 0;
    }
  value = (encoded >> 8u) & 0xffu;
  if (value > AGENTS_STATE_LAST_30_DAYS ||
      (encoded & 0xffu) != ((value ^ 0xffu) & 0xffu))
    {
      return 0;
    }
  *state = value;
  return 1;
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

static ATTR_NOINLINE void *fw_malloc(u32 length)
{
#ifdef AP01_LOADER_SELF_TEST
  extern void *ap01_selftest_malloc(u32);
  return ap01_selftest_malloc(length);
#else
  return ((malloc_fn)VA_MALLOC)(length);
#endif
}

static ATTR_NOINLINE void fw_free(void *pointer)
{
#ifdef AP01_LOADER_SELF_TEST
  extern void ap01_selftest_free(void *);
  ap01_selftest_free(pointer);
#else
  ((free_fn)VA_FREE)(pointer);
#endif
}

static ATTR_NOINLINE int fw_webclient_perform(void *context)
{
#ifdef AP01_LOADER_SELF_TEST
  extern int ap01_selftest_webclient_perform(void *);
  return ap01_selftest_webclient_perform(context);
#else
  return ((webclient_perform_fn)VA_WEBCLIENT_PERFORM)(context);
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

static u32 crc32_update(u32 crc, const u8 *data, u32 length)
{
  u32 index;
  for (index = 0u; index < length; ++index)
    {
      u32 bit;
      crc ^= (u32)data[index];
      for (bit = 0u; bit < 8u; ++bit)
        {
          crc = (crc >> 1u) ^ (0xedb88320u & (0u - (crc & 1u)));
        }
    }
  return crc;
}

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
      read_u16(state->header + 4u) != 2u ||
      read_u16(state->header + 6u) != PACKAGE_HEADER_SIZE ||
      read_u32(state->header + 24u) != PAGE_COUNT ||
      read_u32(state->header + 28u) != 0u)
    {
      return ERR_INVAL;
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
  state->page_crc = 0xffffffffu;
  return 0;
}

static int finish_current_page(struct download_state *state)
{
  u32 actual_crc = state->page_crc ^ 0xffffffffu;
  int close_result = fw_close(state->fd);
  state->fd = -1;
  if (close_result < 0 ||
      state->page_written != state->page_length[state->page_index] ||
      state->gif_header_length != 10u ||
      !gif_header_valid(state->gif_header) ||
      state->last_byte != 0x3bu ||
      actual_crc != read_u32(
          state->header + 48u + state->page_index * 4u))
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
      state->page_crc = crc32_update(
          state->page_crc, data + offset, amount);
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
  if (context == (void *)0)
    {
      return ERR_INVAL;
    }
  state = (struct download_state *)fw_malloc((u32)sizeof(*state));
  if (state == (void *)0)
    {
      return ERR_IO;
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
      result = ERR_IO;
      goto release_state;
    }
  state->slot = next_slot;
  *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = state;
  result = fw_webclient_perform(context);
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
      if (write_record(meta_path, state->generation, state->slot) < 0)
        {
          result = ERR_INVAL;
        }
    }
  else if (result >= 0)
    {
      result = ERR_INVAL;
    }
release_state:
  fw_free(state);
  return result;
}

ATTR_ENTRY int ap01_agents_apply_current(void *argument)
{
  struct stock_pet_state *state = (struct stock_pet_state *)argument;
  struct agents_meta meta;
  u32 agents_state;
  if (state == (void *)0 || state->gif == (void *)0 ||
      !agents_state_decode(state->agents_state, &agents_state) ||
      agents_state == AGENTS_STATE_CLOSED)
    {
      return 0;
    }
  if (read_record(meta_path, &meta) < 0)
    {
      return 1;
    }
  ((gif_set_src_fn)VA_LV_GIF_SET_SRC)(
      state->gif,
      page_path(meta.slot, agents_state - AGENTS_STATE_OVERVIEW));
  if (*(void **)((u8 *)state->gif + 0x5cu) == (void *)0)
    {
      return 0;
    }
  (void)write_record(ack_path, meta.generation, meta.slot);
  return 1;
}

ATTR_ENTRY void ap01_agents_ui_timer_wrapper(void *timer)
{
  void *theme;
  void *pet;
  void *wrapper;
  struct stock_pet_state *state;
  struct agents_meta meta;
  struct agents_meta ack;
  u32 agents_state;
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
  if (((stock_get_dispatch_fn)VA_STOCK_GET_DISPATCH)(theme) != 7)
    {
      return;
    }
  pet = ((stock_get_child_fn)VA_STOCK_GET_CHILD)(theme, 7);
  if (pet == (void *)0)
    {
      return;
    }
  wrapper = *(void **)((u8 *)pet + 16u);
  if (wrapper == (void *)0 || *(u32 *)wrapper != 10u)
    {
      return;
    }
  state = (struct stock_pet_state *)*(void **)((u8 *)wrapper + 4u);
  if (state == (void *)0 || state->gif == (void *)0)
    {
      return;
    }
  if (!agents_state_decode(state->agents_state, &agents_state))
    {
      (void)ap01_agents_restore_pet(state);
      return;
    }
  if (agents_state == AGENTS_STATE_CLOSED)
    {
      if (*(void **)((u8 *)state->gif + 0x5cu) == (void *)0)
        {
          (void)ap01_agents_restore_pet(state);
        }
      return;
    }
  if (read_record(meta_path, &meta) < 0)
    {
      return;
    }
  if (read_record(ack_path, &ack) == 0 &&
      ack.generation == meta.generation &&
      ack.slot == meta.slot)
    {
      return;
    }
  if (!ap01_agents_apply_current(state))
    {
      (void)ap01_agents_restore_pet(state);
    }
}

ATTR_ENTRY void ap01_agents_loader_end_marker(void)
{
}
