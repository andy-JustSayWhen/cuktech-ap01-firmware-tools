/*
 * AP01 AGENTS four-page package loader.
 *
 * Transport and three-slot publication follow the verified loader in
 * 本项目引用的屏幕控制参考实现。
 */

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long long u64;

#if defined(AP01_CRC_SELF_TEST) || defined(AP01_LOADER_SELF_TEST)
#define ATTR_ENTRY __attribute__((noinline, used))
#else
#define ATTR_ENTRY __attribute__((section(".text.entry"), noinline, used))
#define ATTR_NAKED_ENTRY \
  __attribute__((section(".text.entry"), naked, noinline, used))
#endif
#define ATTR_NOINLINE __attribute__((noinline))

#ifdef AP01_0041
#define VA_STOCK_UI_TIMER                 0xa00af262u
#define VA_STOCK_GET_DISPATCH             0xa00b2ff4u
#define VA_STOCK_GET_CHILD                0xa00b3902u
#define VA_LV_GIF_SET_SRC                 0xa00ed7f4u
#define VA_WEBCLIENT_PERFORM              0xa00efb74u
#define VA_STOCK_LOCATION_LOOKUP          0xa00acbeau
#define VA_STOCK_WEATHER_STATE            0x62fca650u
#define VA_OPEN                           0xa003f4f6u
#define VA_CLOSE                          0xa0026888u
#define VA_READ                           0xa003f6a2u
#define VA_WRITE                          0xa0027e94u
#define VA_MALLOC                         0xa008e362u
#define VA_FREE                           0xa008ac12u
#define VA_STOCK_WEATHER_TIMER_GLOBAL     0x62fc9520u
#define VA_STOCK_TIMER_INIT               0xa009e106u
#define VA_STOCK_TIMER_SCHEDULE           0xa009e146u
#else
#define VA_STOCK_UI_TIMER                 0xa00bb5dau
#define VA_STOCK_GET_DISPATCH             0xa00be388u
#define VA_STOCK_GET_CHILD                0xa00be3cau
#define VA_LV_GIF_SET_SRC                 0xa00cf8d8u
#define VA_WEBCLIENT_PERFORM              0xa00d86bau
#define VA_STOCK_LOCATION_LOOKUP          0xa00acbeau
#define VA_STOCK_WEATHER_STATE            0x62fca650u
#define VA_OPEN                           0xa003f448u
#define VA_CLOSE                          0xa0026788u
#define VA_READ                           0xa003f5f4u
#define VA_WRITE                          0xa0027d94u
#define VA_MALLOC                         0xa007e1c4u
#define VA_FREE                           0xa007c256u
#define VA_STOCK_WEATHER_TIMER_GLOBAL     0x62fca9a8u
#define VA_STOCK_TIMER_INIT               0xa009b376u
#define VA_STOCK_TIMER_SCHEDULE           0xa009b3b6u
#endif

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
#ifdef AP01_LOADER_SELF_TEST
#define WEBCLIENT_SINK_OFFSET             48u
#else
#define WEBCLIENT_SINK_OFFSET             60u
#endif
#define WEBCLIENT_HTTP_STATUS_OFFSET      96u
#define WEBCLIENT_URL_OFFSET              8u
#define WEBCLIENT_TIMEOUT_OFFSET          36u
#define WEBCLIENT_WORK_STATE_OFFSET       108u
#ifdef AP01_LOADER_SELF_TEST
/* 主机自测是 64 位指针：method/buffer/ready 若沿用固件的 +4/+48/+112 偏移，
   会与 url(+8)、sink(+48)、work_state(+108) 的 8 字节指针写各重叠 4 字节
   （固件 32 位指针无此问题）。参照 SINK_OFFSET 的既有做法，自测改用
   116 字节上下文内互不重叠的空闲偏移；固件构建保持原厂布局不变。 */
#define WEBCLIENT_METHOD_OFFSET           16u
#define WEBCLIENT_BUFFER_OFFSET           24u
#define WEBCLIENT_BUFFER_SIZE_OFFSET      32u
#define WEBCLIENT_READY_OFFSET            40u
#else
#define WEBCLIENT_METHOD_OFFSET           4u
#define WEBCLIENT_BUFFER_OFFSET           48u
#define WEBCLIENT_BUFFER_SIZE_OFFSET      52u
#define WEBCLIENT_READY_OFFSET            112u
#endif
#define WEBCLIENT_CONTEXT_BYTES           116u

#ifndef AP01_AGENTS_ENDPOINT_COUNT
#define AP01_AGENTS_ENDPOINT_COUNT        0u
#endif
#ifndef AP01_AGENTS_DISABLE_DOWNLOAD
#define AP01_AGENTS_DISABLE_DOWNLOAD      0u
#endif

#ifndef AP01_AGENTS_ENDPOINT_TIMEOUT_SECONDS
#define AP01_AGENTS_ENDPOINT_TIMEOUT_SECONDS 0u
#endif

#ifndef AP01_AGENTS_WEATHER_COEXISTENCE
#define AP01_AGENTS_WEATHER_COEXISTENCE   0u
#endif

#ifndef AP01_AGENTS_WEATHER_DUAL_REQUEST
#define AP01_AGENTS_WEATHER_DUAL_REQUEST  0u
#endif

#ifndef AP01_AGENTS_WEATHER_SUCCESS_REQUIRES_STOCK
#define AP01_AGENTS_WEATHER_SUCCESS_REQUIRES_STOCK 0u
#endif

#ifndef AP01_AGENTS_STOCK_WEATHER_FIRST
#define AP01_AGENTS_STOCK_WEATHER_FIRST 0u
#endif

#ifndef AP01_AGENTS_WEATHER_SOLO_REQUEST
#define AP01_AGENTS_WEATHER_SOLO_REQUEST 0u
#endif

#ifndef AP01_AGENTS_POST_WEATHER_FETCH
#define AP01_AGENTS_POST_WEATHER_FETCH 0u
#endif

#ifndef AP01_AGENTS_STANDALONE_TIMER
#define AP01_AGENTS_STANDALONE_TIMER 0u
#endif

#ifndef AP01_AGENTS_REFRESH_SECONDS
#define AP01_AGENTS_REFRESH_SECONDS 300u
#endif

#ifndef AP01_AGENTS_LOCATION_SLOT_DASHBOARD
#define AP01_AGENTS_LOCATION_SLOT_DASHBOARD 0u
#endif

#ifndef AP01_AGENTS_ROUND_DIAGNOSTIC
#define AP01_AGENTS_ROUND_DIAGNOSTIC      0u
#endif

#ifndef AP01_AGENTS_DOWNLOAD_DIAGNOSTIC
#define AP01_AGENTS_DOWNLOAD_DIAGNOSTIC   0u
#endif

#ifndef AP01_AGENTS_RESULT_DIAGNOSTIC
#define AP01_AGENTS_RESULT_DIAGNOSTIC     0u
#endif

#ifndef AP01_AGENTS_PUBLISH_DIAGNOSTIC
#define AP01_AGENTS_PUBLISH_DIAGNOSTIC    0u
#endif
#ifndef AP01_AGENTS_ADOPTION_DIAGNOSTIC
#define AP01_AGENTS_ADOPTION_DIAGNOSTIC   0u
#endif

#define TRANSPORT_MODE_WEATHER             0u
#define TRANSPORT_MODE_AGENTS_RETRY_WEATHER 1u
#define TRANSPORT_MODE_AGENTS_ONLY         2u
#define STOCK_CITY_READY_MS               100000u

#define GIF_PARSE_SKIP_MASK               0x000003ffu
#define GIF_PARSE_STATE_SHIFT             10u
#define GIF_PARSE_STATE_MASK              0x00003c00u
#define GIF_PARSE_FRAMES_SHIFT            14u
#define GIF_PARSE_FRAMES_MASK             0x0000c000u

#define GIF_STATE_HEADER                  0u
#define GIF_STATE_GLOBAL_COLOR_TABLE      1u
#define GIF_STATE_BLOCK                   2u
#define GIF_STATE_EXTENSION_LABEL         3u
#define GIF_STATE_SUBBLOCK_SIZE           4u
#define GIF_STATE_SUBBLOCK_DATA           5u
#define GIF_STATE_IMAGE_DESCRIPTOR        6u
#define GIF_STATE_LOCAL_COLOR_TABLE       7u
#define GIF_STATE_LZW_CODE_SIZE           8u
#define GIF_STATE_DONE                    9u

typedef void (*void_one_arg_fn)(void *);
typedef int (*stock_get_dispatch_fn)(void *);
typedef void *(*stock_get_child_fn)(void *, int);
typedef void (*gif_set_src_fn)(void *, const void *);
typedef int (*webclient_perform_fn)(void *);
typedef int (*stock_location_lookup_fn)(void *);
typedef int (*open_fn)(const char *, int, int);
typedef int (*close_fn)(int);
typedef int (*io_fn)(int, void *, u32);
typedef int (*write_fn)(int, const void *, u32);
typedef void *(*malloc_fn)(u32);
typedef void (*free_fn)(void *);
typedef void (*void_two_arg_fn)(void *, void *);
typedef int (*timer_schedule_fn)(void *, void *, u32, u32, u32, u32);

static ATTR_NOINLINE int fw_webclient_perform(void *context);
static int write_record(const char *path, u32 generation, u32 slot);

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
  u32 gif_parse;
  u32 complete;
  u8 gif_header[10];
  u8 gif_packed;
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

#if AP01_AGENTS_WEATHER_COEXISTENCE
static volatile u32 agents_transport_mode =
    TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
static volatile u32 agents_next_transport_mode =
    TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
#endif

#if AP01_AGENTS_ROUND_DIAGNOSTIC || AP01_AGENTS_DOWNLOAD_DIAGNOSTIC || \
    AP01_AGENTS_RESULT_DIAGNOSTIC || AP01_AGENTS_PUBLISH_DIAGNOSTIC || \
    AP01_AGENTS_ADOPTION_DIAGNOSTIC
static volatile u32 agents_diagnostic_stage;
static u32 agents_diagnostic_displayed_stage = 0xffffffffu;
extern const u8 agents_fallback_overview_descriptor[];
extern const u8 agents_fallback_weekly_descriptor[];
extern const u8 agents_fallback_today_descriptor[];
extern const u8 agents_fallback_last_30_days_descriptor[];

#if AP01_AGENTS_ROUND_DIAGNOSTIC || AP01_AGENTS_DOWNLOAD_DIAGNOSTIC
static ATTR_NOINLINE void agents_diagnostic_advance(u32 stage)
{
  if (agents_diagnostic_stage < stage)
    {
      agents_diagnostic_stage = stage;
    }
}
#endif

static ATTR_NOINLINE void agents_diagnostic_set_source(
    void *gif,
    const void *source)
{
#ifdef AP01_LOADER_SELF_TEST
  extern void ap01_selftest_gif_set_src(void *, const void *);
  ap01_selftest_gif_set_src(gif, source);
#else
  ((gif_set_src_fn)VA_LV_GIF_SET_SRC)(gif, source);
#endif
}

static ATTR_NOINLINE void agents_diagnostic_show(void *gif)
{
  u32 stage = agents_diagnostic_stage;
  const void *source;
  if (gif == (void *)0 || stage == agents_diagnostic_displayed_stage)
    {
      return;
    }
  if (stage == 0u)
    {
      source = agents_fallback_overview_descriptor;
    }
  else if (stage == 1u)
    {
      source = agents_fallback_weekly_descriptor;
    }
  else if (stage == 2u)
    {
      source = agents_fallback_today_descriptor;
    }
  else
    {
      source = agents_fallback_last_30_days_descriptor;
    }
  agents_diagnostic_set_source(gif, source);
  if (*(void **)((u8 *)gif + 0x5cu) != (void *)0)
    {
      agents_diagnostic_displayed_stage = stage;
    }
}

#if AP01_AGENTS_RESULT_DIAGNOSTIC
static ATTR_NOINLINE int agents_result_diagnostic_perform(void *context)
{
  int result = fw_webclient_perform(context);
  if (result < 0)
    {
      return result;
    }
  if (agents_diagnostic_stage < 1u)
    {
      agents_diagnostic_stage = 1u;
    }
  if (*(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) != 200u)
    {
      return result;
    }
  if (agents_diagnostic_stage < 2u)
    {
      agents_diagnostic_stage = 2u;
    }
  return result;
}

static ATTR_NOINLINE int agents_result_diagnostic_write_record(
    const char *path,
    u32 generation,
    u32 slot)
{
  agents_diagnostic_stage = 3u;
  return write_record(path, generation, slot);
}
#endif
#endif

#if AP01_AGENTS_ENDPOINT_COUNT > 0u
static const char endpoint_1[] = AP01_AGENTS_ENDPOINT_1;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 1u
static const char endpoint_2[] = AP01_AGENTS_ENDPOINT_2;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 2u
static const char endpoint_3[] = AP01_AGENTS_ENDPOINT_3;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 3u
static const char endpoint_4[] = AP01_AGENTS_ENDPOINT_4;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 4u
static const char endpoint_5[] = AP01_AGENTS_ENDPOINT_5;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 5u
static const char endpoint_6[] = AP01_AGENTS_ENDPOINT_6;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 6u
static const char endpoint_7[] = AP01_AGENTS_ENDPOINT_7;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 7u
static const char endpoint_8[] = AP01_AGENTS_ENDPOINT_8;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 8u
static const char endpoint_9[] = AP01_AGENTS_ENDPOINT_9;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 9u
static const char endpoint_10[] = AP01_AGENTS_ENDPOINT_10;
#endif

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

#if AP01_AGENTS_WEATHER_COEXISTENCE && !AP01_AGENTS_LOCATION_SLOT_DASHBOARD
static ATTR_NOINLINE int fw_stock_location_lookup(void *target)
{
#ifdef AP01_LOADER_SELF_TEST
  extern int ap01_selftest_stock_location_lookup(void *);
  return ap01_selftest_stock_location_lookup(target);
#else
  return ((stock_location_lookup_fn)VA_STOCK_LOCATION_LOOKUP)(target);
#endif
}
#endif

#if AP01_AGENTS_WEATHER_COEXISTENCE && !AP01_AGENTS_LOCATION_SLOT_DASHBOARD && \
    !AP01_AGENTS_STOCK_WEATHER_FIRST
static ATTR_NOINLINE u32 fw_stock_weather_uptime_ms(void)
{
#ifdef AP01_LOADER_SELF_TEST
  extern u32 ap01_selftest_weather_uptime_ms(void);
  return ap01_selftest_weather_uptime_ms();
#else
  volatile u32 *value = (volatile u32 *)(VA_STOCK_WEATHER_STATE + 196u);
  return *value;
#endif
}
#endif

#if AP01_AGENTS_WEATHER_COEXISTENCE
static ATTR_NOINLINE int fw_stock_weather_city_present(void)
{
#ifdef AP01_LOADER_SELF_TEST
  extern int ap01_selftest_weather_city_present(void);
  return ap01_selftest_weather_city_present();
#else
  volatile u8 *state = (volatile u8 *)VA_STOCK_WEATHER_STATE;
  return state[68] != 0u || state[132] != 0u;
#endif
}
#endif

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

static __attribute__((unused)) const char *endpoint_at(u32 index)
{
  (void)index;
#if AP01_AGENTS_ENDPOINT_COUNT > 0u
  if (index == 0u) return endpoint_1;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 1u
  if (index == 1u) return endpoint_2;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 2u
  if (index == 2u) return endpoint_3;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 3u
  if (index == 3u) return endpoint_4;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 4u
  if (index == 4u) return endpoint_5;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 5u
  if (index == 5u) return endpoint_6;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 6u
  if (index == 6u) return endpoint_7;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 7u
  if (index == 7u) return endpoint_8;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 8u
  if (index == 8u) return endpoint_9;
#endif
#if AP01_AGENTS_ENDPOINT_COUNT > 9u
  if (index == 9u) return endpoint_10;
#endif
  return (const char *)0;
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

#if AP01_AGENTS_PUBLISH_DIAGNOSTIC || AP01_AGENTS_ADOPTION_DIAGNOSTIC
static ATTR_NOINLINE int write_record_diagnostic(
    const char *path, u32 generation, u32 slot)
{
  struct agents_meta meta;
  struct agents_meta observed;
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
#if AP01_AGENTS_PUBLISH_DIAGNOSTIC
  agents_diagnostic_stage = 1u;
#endif
  result = write_all(fd, &meta, (u32)sizeof(meta));
  if (result >= 0)
    {
#if AP01_AGENTS_PUBLISH_DIAGNOSTIC
      agents_diagnostic_stage = 2u;
#endif
    }
  if (fw_close(fd) < 0)
    {
      result = ERR_IO;
    }
  else if (result >= 0)
    {
#if AP01_AGENTS_PUBLISH_DIAGNOSTIC
      agents_diagnostic_stage = 3u;
#endif
    }
  if (result < 0 || read_record(path, &observed) < 0 ||
      observed.generation != generation || observed.slot != slot)
    {
      return ERR_INVAL;
    }
#if AP01_AGENTS_ADOPTION_DIAGNOSTIC
  agents_diagnostic_stage = 1u;
#endif
  return 0;
}
#endif

static __attribute__((unused)) int clear_slot(u32 slot)
{
  u32 page;
  int result = 0;
  for (page = 0u; page < PAGE_COUNT; ++page)
    {
      int fd = fw_open(
          page_path(slot, page),
          AP01_O_RDWR_CREAT_TRUNC,
          AP01_MODE_0666);
      if (fd < 0)
        {
          result = ERR_IO;
        }
      else if (fw_close(fd) < 0)
        {
          result = ERR_IO;
        }
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

static u32 gif_parse_state(const struct download_state *state)
{
  return (state->gif_parse & GIF_PARSE_STATE_MASK) >>
         GIF_PARSE_STATE_SHIFT;
}

static u32 gif_parse_skip(const struct download_state *state)
{
  return state->gif_parse & GIF_PARSE_SKIP_MASK;
}

static u32 gif_parse_frames(const struct download_state *state)
{
  return (state->gif_parse & GIF_PARSE_FRAMES_MASK) >>
         GIF_PARSE_FRAMES_SHIFT;
}

static void gif_parse_transition(struct download_state *state,
                                 u32 next_state, u32 skip)
{
  state->gif_parse =
      (state->gif_parse & GIF_PARSE_FRAMES_MASK) |
      ((next_state << GIF_PARSE_STATE_SHIFT) & GIF_PARSE_STATE_MASK) |
      (skip & GIF_PARSE_SKIP_MASK);
}

static void gif_parse_add_frame(struct download_state *state)
{
  u32 frames = gif_parse_frames(state);
  if (frames < 3u)
    {
      frames += 1u;
    }
  state->gif_parse =
      (state->gif_parse & ~GIF_PARSE_FRAMES_MASK) |
      (frames << GIF_PARSE_FRAMES_SHIFT);
}

static u32 gif_color_table_bytes(u8 packed)
{
  return 3u << (((u32)packed & 7u) + 1u);
}

static int gif_consume_byte(struct download_state *state,
                            u32 page_offset, u8 value)
{
  u32 parse_state;
  u32 skip;
  if (page_offset < 10u)
    {
      state->gif_header[page_offset] = value;
      return 0;
    }
  if (page_offset < 13u)
    {
      if (page_offset == 10u)
        {
          state->gif_packed = value;
        }
      if (page_offset == 12u)
        {
          if ((state->gif_packed & 0x80u) != 0u)
            {
              gif_parse_transition(
                  state,
                  GIF_STATE_GLOBAL_COLOR_TABLE,
                  gif_color_table_bytes(state->gif_packed));
            }
          else
            {
              gif_parse_transition(state, GIF_STATE_BLOCK, 0u);
            }
        }
      return 0;
    }

  parse_state = gif_parse_state(state);
  skip = gif_parse_skip(state);
  if (parse_state == GIF_STATE_GLOBAL_COLOR_TABLE)
    {
      if (skip == 0u) return ERR_INVAL;
      gif_parse_transition(
          state, skip == 1u ? GIF_STATE_BLOCK : parse_state, skip - 1u);
      return 0;
    }
  if (parse_state == GIF_STATE_BLOCK)
    {
      if (value == 0x2cu)
        {
          gif_parse_add_frame(state);
          gif_parse_transition(state, GIF_STATE_IMAGE_DESCRIPTOR, 9u);
          return 0;
        }
      if (value == 0x21u)
        {
          gif_parse_transition(state, GIF_STATE_EXTENSION_LABEL, 0u);
          return 0;
        }
      if (value == 0x3bu)
        {
          gif_parse_transition(state, GIF_STATE_DONE, 0u);
          return 0;
        }
      return ERR_INVAL;
    }
  if (parse_state == GIF_STATE_EXTENSION_LABEL)
    {
      gif_parse_transition(state, GIF_STATE_SUBBLOCK_SIZE, 0u);
      return 0;
    }
  if (parse_state == GIF_STATE_SUBBLOCK_SIZE)
    {
      gif_parse_transition(
          state,
          value == 0u ? GIF_STATE_BLOCK : GIF_STATE_SUBBLOCK_DATA,
          (u32)value);
      return 0;
    }
  if (parse_state == GIF_STATE_SUBBLOCK_DATA)
    {
      if (skip == 0u) return ERR_INVAL;
      gif_parse_transition(
          state,
          skip == 1u ? GIF_STATE_SUBBLOCK_SIZE : parse_state,
          skip - 1u);
      return 0;
    }
  if (parse_state == GIF_STATE_IMAGE_DESCRIPTOR)
    {
      if (skip == 0u) return ERR_INVAL;
      if (skip == 1u)
        {
          if ((value & 0x80u) != 0u)
            {
              gif_parse_transition(
                  state,
                  GIF_STATE_LOCAL_COLOR_TABLE,
                  gif_color_table_bytes(value));
            }
          else
            {
              gif_parse_transition(state, GIF_STATE_LZW_CODE_SIZE, 0u);
            }
        }
      else
        {
          gif_parse_transition(state, parse_state, skip - 1u);
        }
      return 0;
    }
  if (parse_state == GIF_STATE_LOCAL_COLOR_TABLE)
    {
      if (skip == 0u) return ERR_INVAL;
      gif_parse_transition(
          state,
          skip == 1u ? GIF_STATE_LZW_CODE_SIZE : parse_state,
          skip - 1u);
      return 0;
    }
  if (parse_state == GIF_STATE_LZW_CODE_SIZE)
    {
      if (value < 2u || value > 8u) return ERR_INVAL;
      gif_parse_transition(state, GIF_STATE_SUBBLOCK_SIZE, 0u);
      return 0;
    }
  return ERR_INVAL;
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
  state->gif_parse = 0u;
  state->gif_packed = 0u;
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
      state->page_written < GIF_MIN_BYTES ||
      !gif_header_valid(state->gif_header) ||
      gif_parse_state(state) != GIF_STATE_DONE ||
      gif_parse_frames(state) < 2u ||
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
      u32 page_offset;
      for (page_offset = 0u; page_offset < amount; ++page_offset)
        {
          if (gif_consume_byte(
                  state,
                  state->page_written + page_offset,
                  data[offset + page_offset]) < 0)
            {
              return ERR_INVAL;
            }
        }
      state->page_crc = crc32_update(
          state->page_crc, data + offset, amount);
      if (write_all(state->fd, data + offset, amount) < 0)
        {
          return ERR_IO;
        }
      state->page_written += amount;
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

ATTR_ENTRY int ap01_agents_location_stub(void *target)
{
  volatile u8 *text = (volatile u8 *)target;
#if AP01_AGENTS_ROUND_DIAGNOSTIC
  agents_diagnostic_advance(1u);
#endif
  if (text == (void *)0)
    {
      return 0;
    }
#if AP01_AGENTS_WEATHER_COEXISTENCE
#if AP01_AGENTS_LOCATION_SLOT_DASHBOARD
  if (agents_next_transport_mode == TRANSPORT_MODE_AGENTS_RETRY_WEATHER)
    {
      agents_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
      agents_next_transport_mode = TRANSPORT_MODE_WEATHER;
    }
  else if (fw_stock_weather_city_present())
    {
      agents_transport_mode = TRANSPORT_MODE_WEATHER;
      agents_next_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
      return 0;
    }
  else
    {
      agents_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
      agents_next_transport_mode = TRANSPORT_MODE_WEATHER;
    }
#else
#if !AP01_AGENTS_STOCK_WEATHER_FIRST
  if (agents_next_transport_mode == TRANSPORT_MODE_AGENTS_RETRY_WEATHER)
    {
      agents_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
      agents_next_transport_mode = TRANSPORT_MODE_WEATHER;
    }
  else
#endif
  if (fw_stock_location_lookup(target) != 0)
    {
      agents_transport_mode = TRANSPORT_MODE_WEATHER;
#if AP01_AGENTS_STOCK_WEATHER_FIRST
      agents_next_transport_mode = TRANSPORT_MODE_WEATHER;
#else
      agents_next_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
#endif
      return 1;
    }
  else if (fw_stock_weather_city_present())
    {
#if AP01_AGENTS_STOCK_WEATHER_FIRST
      agents_transport_mode = TRANSPORT_MODE_WEATHER;
      agents_next_transport_mode = TRANSPORT_MODE_WEATHER;
      return 0;
#else
      if (fw_stock_weather_uptime_ms() > STOCK_CITY_READY_MS)
        {
          agents_transport_mode = TRANSPORT_MODE_WEATHER;
          agents_next_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
          return 0;
        }
#if AP01_AGENTS_WEATHER_SUCCESS_REQUIRES_STOCK
      agents_transport_mode = TRANSPORT_MODE_WEATHER;
      agents_next_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
      return 0;
#else
      agents_transport_mode = TRANSPORT_MODE_AGENTS_ONLY;
      agents_next_transport_mode = TRANSPORT_MODE_WEATHER;
#endif
#endif
    }
  else
    {
#if AP01_AGENTS_STOCK_WEATHER_FIRST
      agents_transport_mode = TRANSPORT_MODE_WEATHER;
      agents_next_transport_mode = TRANSPORT_MODE_WEATHER;
      return 0;
#elif AP01_AGENTS_WEATHER_SUCCESS_REQUIRES_STOCK
      agents_transport_mode = TRANSPORT_MODE_WEATHER;
      agents_next_transport_mode = TRANSPORT_MODE_AGENTS_RETRY_WEATHER;
      return 0;
#else
      agents_transport_mode = TRANSPORT_MODE_AGENTS_ONLY;
      agents_next_transport_mode = TRANSPORT_MODE_WEATHER;
#endif
    }
#endif
#endif
  text[0] = (u8)'0';
  text[1] = (u8)'0';
  text[2] = (u8)'0';
  text[3] = (u8)'0';
  text[4] = (u8)'0';
  text[5] = (u8)'0';
  text[6] = (u8)'0';
  text[7] = (u8)'0';
  text[8] = (u8)'0';
  text[9] = 0u;
  return 1;
}

static ATTR_NOINLINE int ap01_agents_download_package(void *context)
{
#if AP01_AGENTS_DISABLE_DOWNLOAD
  /* 公开固件编译期禁用下载。不用静态变量做运行时开关：.data/.bss 初值
     不进只读载荷，运行时实读原厂字节（见取证文档第 3 节实测）。
     volatile 写入只为让桩函数带可观察副作用，防止编译器把取包定时器
     回调里对桩函数的调用整体删除——公开固件保持"定时器照常回调、
     每次只调桩函数、不产生任何网络请求"的结构（DESIGN 9.5）。 */
  if (context != (void *)0)
    {
      *(volatile u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) = 0u;
    }
  return ERR_INVAL;
#else
  struct agents_meta old_meta;
  struct agents_meta old_ack;
  struct download_state *state;
  u32 next_slot;
  u32 have_meta;
  u32 have_ack;
  u32 endpoint_index;
  u32 attempt_count;
  const char *original_url;
  u32 original_timeout;
  int result = ERR_IO;
#if AP01_AGENTS_DOWNLOAD_DIAGNOSTIC || AP01_AGENTS_RESULT_DIAGNOSTIC || \
    AP01_AGENTS_PUBLISH_DIAGNOSTIC || AP01_AGENTS_ADOPTION_DIAGNOSTIC
  agents_diagnostic_stage = 0u;
  agents_diagnostic_displayed_stage = 0xffffffffu;
#elif AP01_AGENTS_ROUND_DIAGNOSTIC
  agents_diagnostic_advance(3u);
#endif
  if (context == (void *)0)
    {
      return ERR_INVAL;
    }
  original_url = *(const char **)((u8 *)context + WEBCLIENT_URL_OFFSET);
  original_timeout = *(u32 *)((u8 *)context + WEBCLIENT_TIMEOUT_OFFSET);
  state = (struct download_state *)fw_malloc((u32)sizeof(*state));
  if (state == (void *)0)
    {
      return ERR_IO;
    }
#if AP01_AGENTS_DOWNLOAD_DIAGNOSTIC
  agents_diagnostic_advance(1u);
#endif
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
  attempt_count = AP01_AGENTS_ENDPOINT_COUNT > 0u ?
                  AP01_AGENTS_ENDPOINT_COUNT : 1u;
  for (endpoint_index = 0u; endpoint_index < attempt_count; ++endpoint_index)
    {
      const char *endpoint = endpoint_at(endpoint_index);
      int close_result = 0;
      int published = 0;
      memory_zero(state, (u32)sizeof(*state));
      state->fd = -1;
      state->slot = next_slot;
      if (endpoint != (const char *)0)
        {
          *(const char **)((u8 *)context + WEBCLIENT_URL_OFFSET) = endpoint;
        }
      if (AP01_AGENTS_ENDPOINT_TIMEOUT_SECONDS > 0u)
        {
          *(u32 *)((u8 *)context + WEBCLIENT_TIMEOUT_OFFSET) =
              AP01_AGENTS_ENDPOINT_TIMEOUT_SECONDS;
        }
      *(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) = 0u;
      *(void **)((u8 *)context + WEBCLIENT_WORK_STATE_OFFSET) = (void *)0;
      *(void **)((u8 *)context + WEBCLIENT_SINK_OFFSET) =
          (void *)ap01_agents_sink;
      *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = state;
#if AP01_AGENTS_DOWNLOAD_DIAGNOSTIC
      if (endpoint_index == 0u)
        {
          agents_diagnostic_advance(2u);
        }
#endif
#if AP01_AGENTS_RESULT_DIAGNOSTIC
      result = agents_result_diagnostic_perform(context);
#else
      result = fw_webclient_perform(context);
#endif
#if AP01_AGENTS_DOWNLOAD_DIAGNOSTIC
      if (endpoint_index == 0u)
        {
          agents_diagnostic_advance(3u);
        }
#endif
      *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = (void *)0;
      *(void **)((u8 *)context + WEBCLIENT_WORK_STATE_OFFSET) = (void *)0;
      if (state->fd >= 0)
        {
          close_result = fw_close(state->fd);
          state->fd = -1;
        }
      if (result >= 0 &&
          *(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) == 200u &&
          close_result >= 0 &&
          state->complete != 0u &&
          state->total == state->expected_total &&
#if AP01_AGENTS_RESULT_DIAGNOSTIC
          agents_result_diagnostic_write_record(
              meta_path, state->generation, state->slot) == 0)
#elif AP01_AGENTS_PUBLISH_DIAGNOSTIC || AP01_AGENTS_ADOPTION_DIAGNOSTIC
          write_record_diagnostic(
              meta_path, state->generation, state->slot) == 0)
#else
          write_record(meta_path, state->generation, state->slot) == 0)
#endif
        {
          published = 1;
        }
      else if (result >= 0)
        {
          result = ERR_INVAL;
        }
      if (published != 0)
        {
          break;
        }
      if (clear_slot(state->slot) < 0 && result >= 0)
        {
          result = ERR_IO;
        }
    }
  *(const char **)((u8 *)context + WEBCLIENT_URL_OFFSET) = original_url;
  *(u32 *)((u8 *)context + WEBCLIENT_TIMEOUT_OFFSET) = original_timeout;
  *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = (void *)0;
  *(void **)((u8 *)context + WEBCLIENT_WORK_STATE_OFFSET) = (void *)0;
release_state:
  fw_free(state);
  return result;
#endif
}

#if AP01_AGENTS_POST_WEATHER_FETCH && \
    !defined(AP01_CRC_SELF_TEST) && !defined(AP01_LOADER_SELF_TEST)
static ATTR_NOINLINE __attribute__((used)) void
ap01_agents_post_weather_download(void *context)
{
  void *original_sink;
  void *original_sink_arg;
  u32 weather_status;
  if (context == (void *)0)
    {
      return;
    }
  original_sink = *(void **)((u8 *)context + WEBCLIENT_SINK_OFFSET);
  original_sink_arg = *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET);
  weather_status = *(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET);
  (void)ap01_agents_download_package(context);
  *(void **)((u8 *)context + WEBCLIENT_SINK_OFFSET) = original_sink;
  *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = original_sink_arg;
  *(void **)((u8 *)context + WEBCLIENT_WORK_STATE_OFFSET) = (void *)0;
  *(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) = weather_status;
}

ATTR_NAKED_ENTRY void ap01_agents_post_weather_fetch_entry(void)
{
  __asm__ volatile (
      "mv x23, x10\n"
      "addi x10, x8, -436\n"
      "call ap01_agents_post_weather_download\n"
      "lw x10, 1904(x18)\n"
      "lui x5, 0xa00b7\n"
      "addi x5, x5, 0x260\n"
      "jr x5\n"
  );
}
#endif

ATTR_ENTRY int ap01_agents_webclient_wrapper(void *context)
{
#if AP01_AGENTS_STANDALONE_TIMER
  return fw_webclient_perform(context);
#elif AP01_AGENTS_WEATHER_COEXISTENCE
  const char *original_url;
  void *original_sink;
  void *original_sink_arg;
  u32 original_timeout;
  u32 transport_mode;
  int agents_result;
#if AP01_AGENTS_WEATHER_DUAL_REQUEST
  u32 weather_status = 0u;
  int weather_result = ERR_IO;
#endif
#if AP01_AGENTS_ROUND_DIAGNOSTIC
  agents_diagnostic_advance(2u);
#endif
  if (context == (void *)0)
    {
      return ERR_INVAL;
    }
  transport_mode = agents_transport_mode;
  original_url = *(const char **)((u8 *)context + WEBCLIENT_URL_OFFSET);
  original_sink = *(void **)((u8 *)context + WEBCLIENT_SINK_OFFSET);
  original_sink_arg = *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET);
  original_timeout = *(u32 *)((u8 *)context + WEBCLIENT_TIMEOUT_OFFSET);
  if (transport_mode == TRANSPORT_MODE_WEATHER)
    {
#if AP01_AGENTS_WEATHER_DUAL_REQUEST
      weather_result = fw_webclient_perform(context);
      weather_status = *(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET);
#if AP01_AGENTS_WEATHER_SOLO_REQUEST
      *(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) = weather_status;
      return weather_result;
#endif
      *(void **)((u8 *)context + WEBCLIENT_WORK_STATE_OFFSET) = (void *)0;
#else
      return fw_webclient_perform(context);
#endif
    }
  agents_result = ap01_agents_download_package(context);
  *(const char **)((u8 *)context + WEBCLIENT_URL_OFFSET) = original_url;
  *(u32 *)((u8 *)context + WEBCLIENT_TIMEOUT_OFFSET) = original_timeout;
  *(void **)((u8 *)context + WEBCLIENT_SINK_OFFSET) = original_sink;
  *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = original_sink_arg;
  *(void **)((u8 *)context + WEBCLIENT_WORK_STATE_OFFSET) = (void *)0;
#if AP01_AGENTS_WEATHER_DUAL_REQUEST
  if (transport_mode == TRANSPORT_MODE_WEATHER)
    {
      *(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) = weather_status;
      return weather_result;
    }
#endif
  if (transport_mode == TRANSPORT_MODE_AGENTS_RETRY_WEATHER
#if AP01_AGENTS_WEATHER_SUCCESS_REQUIRES_STOCK
      || transport_mode == TRANSPORT_MODE_AGENTS_ONLY
#endif
      )
    {
      *(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) = 0u;
      return ERR_IO;
    }
  return agents_result;
#else
  return ap01_agents_download_package(context);
#endif
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
#if AP01_AGENTS_ADOPTION_DIAGNOSTIC
  agents_diagnostic_stage = 3u;
  agents_diagnostic_displayed_stage = 0xffffffffu;
  agents_diagnostic_show(state->gif);
#endif
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

#if AP01_AGENTS_STANDALONE_TIMER

#define AGENTS_TIMER_STRUCT_BYTES         0x58u
#define AGENTS_TIMER_FIRST_DELAY_MS       2000u
#define AGENTS_TIMER_PROBE_LIMIT          64u
#define AGENTS_WEBCLIENT_BUFFER_BYTES     4096u
#define AGENTS_STOCK_REQUEST_TIMEOUT_SECONDS 5u

static const char agents_http_get_method[] = "GET";

static ATTR_NOINLINE int fw_stock_timer_loop(void **loop)
{
#ifdef AP01_LOADER_SELF_TEST
  extern int ap01_selftest_stock_timer_loop(void **);
  return ap01_selftest_stock_timer_loop(loop);
#else
  volatile u8 *weather_timer = (volatile u8 *)VA_STOCK_WEATHER_TIMER_GLOBAL;
  volatile void *candidate;
  if (weather_timer[8] != 0x0du)
    {
      return -1;
    }
  candidate = *(volatile void **)(weather_timer + 4u);
  if (candidate == (void *)0)
    {
      return -1;
    }
  *loop = (void *)candidate;
  return 0;
#endif
}

static ATTR_NOINLINE void fw_stock_timer_init(void *loop, void *timer)
{
#ifdef AP01_LOADER_SELF_TEST
  extern void ap01_selftest_stock_timer_init(void *, void *);
  ap01_selftest_stock_timer_init(loop, timer);
#else
  ((void_two_arg_fn)VA_STOCK_TIMER_INIT)(loop, timer);
#endif
}

static ATTR_NOINLINE int fw_stock_timer_schedule(
    void *timer, void *callback, u32 delay_ms)
{
#ifdef AP01_LOADER_SELF_TEST
  extern int ap01_selftest_stock_timer_schedule(void *, void *, u32);
  return ap01_selftest_stock_timer_schedule(timer, callback, delay_ms);
#else
  return ((timer_schedule_fn)VA_STOCK_TIMER_SCHEDULE)(
      timer, callback, delay_ms, 0u, 0u, 0u);
#endif
}

ATTR_ENTRY void ap01_agents_standalone_timer_cb(void *handle)
{
  u8 *context;
  void *buffer;

  if (handle == (void *)0)
    {
      return;
    }
  context = (u8 *)fw_malloc(WEBCLIENT_CONTEXT_BYTES);
  if (context != (u8 *)0)
    {
      memory_zero(context, WEBCLIENT_CONTEXT_BYTES);
      *(const char **)(context + WEBCLIENT_METHOD_OFFSET) =
          agents_http_get_method;
      *(u32 *)(context + WEBCLIENT_TIMEOUT_OFFSET) =
          AGENTS_STOCK_REQUEST_TIMEOUT_SECONDS;
      buffer = fw_malloc(AGENTS_WEBCLIENT_BUFFER_BYTES);
      if (buffer != (void *)0)
        {
          *(void **)(context + WEBCLIENT_BUFFER_OFFSET) = buffer;
          *(u32 *)(context + WEBCLIENT_BUFFER_SIZE_OFFSET) =
              AGENTS_WEBCLIENT_BUFFER_BYTES;
          context[WEBCLIENT_READY_OFFSET] = 1u;
          (void)ap01_agents_download_package(context);
          fw_free(buffer);
        }
      fw_free(context);
    }
  (void)fw_stock_timer_schedule(
      handle, (void *)ap01_agents_standalone_timer_cb,
      AP01_AGENTS_REFRESH_SECONDS * 1000u);
}

ATTR_ENTRY void ap01_agents_standalone_timer_ensure(void)
{
  void *loop;
  void *node;
  void *timer;
  u32 hops;

  if (fw_stock_timer_loop(&loop) != 0)
    {
      return;
    }
  node = *(void **)((u8 *)loop + 0x0cu);
  for (hops = 0u;
       hops < AGENTS_TIMER_PROBE_LIMIT &&
       node != (void *)((u8 *)loop + 8u);
       ++hops)
    {
      u8 *handle = (u8 *)node - 0x10u;
      if (handle[8] == 0x0du &&
          *(void **)(handle + 0x30u) ==
              (void *)ap01_agents_standalone_timer_cb)
        {
          return;
        }
      node = *(void **)((u8 *)node + 4u);
    }
  timer = fw_malloc(AGENTS_TIMER_STRUCT_BYTES);
  if (timer == (void *)0)
    {
      return;
    }
  fw_stock_timer_init(loop, timer);
  (void)fw_stock_timer_schedule(
      timer, (void *)ap01_agents_standalone_timer_cb,
      AGENTS_TIMER_FIRST_DELAY_MS);
}

#endif

ATTR_ENTRY void ap01_agents_ui_timer_wrapper(void *timer)
{
  void *theme;
  void *pet;
  void *wrapper;
  struct stock_pet_state *state;
  struct agents_meta meta;
  struct agents_meta ack;
  u32 agents_state;
#if AP01_AGENTS_STANDALONE_TIMER
  ap01_agents_standalone_timer_ensure();
#endif
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
#if AP01_AGENTS_ROUND_DIAGNOSTIC || AP01_AGENTS_DOWNLOAD_DIAGNOSTIC || \
    AP01_AGENTS_RESULT_DIAGNOSTIC || AP01_AGENTS_PUBLISH_DIAGNOSTIC || \
    AP01_AGENTS_ADOPTION_DIAGNOSTIC
      agents_diagnostic_show(state->gif);
#endif
      return;
    }
#if AP01_AGENTS_ADOPTION_DIAGNOSTIC
  agents_diagnostic_stage = 2u;
  agents_diagnostic_displayed_stage = 0xffffffffu;
  agents_diagnostic_show(state->gif);
#endif
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
