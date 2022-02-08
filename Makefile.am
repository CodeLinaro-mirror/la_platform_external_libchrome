ACLOCAL_AMFLAGS := -I m4

AM_CFLAGS := -Wundef \
        -Wstrict-prototypes \
        -Wno-trigraphs \
        -g -O0 \
        $(LOCBASEUTIL_CFLAGS) \
        -fno-inline \
        -fno-short-enums \
        -fpic \
        -fpermissive \
        -D_GNU_SOURCE \
        -DHAVE_CONFIG_H=1 \
        -DBUILD_DIVSUFSORT64 \
        -D_ANDROID_HOST_ \
        -D_aarch64_ \
        -D_ANDROID_ \
        -D__DATE__="Dec 04 2020" \
        -D__TIME__="08:00:00" \
        -I..


AM_CPPFLAGS := \
        -I. \
        -I$(WORKSPACE)/OTA/streaming/external/modp_b64 \
        -I$(WORKSPACE)/OTA/streaming/external/libevent/include \
        -D_FILE_OFFSET_BITS=64 \
        -D_USE_RTTI_FOR_TYPE_TAGS \
        -D_use_allocator="none" \
        -D_ANDROID_HOST_ \
        -D_aarch64_ \
        -D_ANDROID_ \
        -std=c++11 \
        -DUSE_LE_MODE \
        -fpermissive

AUTOMAKE_OPTIONS = subdir-objects

AM_LDFLAGS := -shared -version-info 1:0:0
library_includedir := $(pkgincludedir)

lib_LTLIBRARIES = libchrome.la
libchrome_common_la_SOURCES := base/at_exit.cc \
    base/base64.cc \
    base/base64url.cc \
    base/base_switches.cc \
    base/bind_helpers.cc \
    base/build_time.cc \
    base/callback_helpers.cc \
    base/callback_internal.cc \
    base/command_line.cc \
    base/cpu.cc \
    base/debug/alias.cc \
    base/debug/debugger.cc \
    base/debug/debugger_posix.cc \
    base/debug/stack_trace.cc \
    base/debug/stack_trace_posix.cc \
    base/debug/task_annotator.cc \
    base/environment.cc \
    base/feature_list.cc \
    base/files/file.cc \
    base/files/file_enumerator.cc \
    base/files/file_enumerator_posix.cc \
    base/files/file_path.cc \
    base/files/file_path_constants.cc \
    base/files/file_path_watcher.cc \
    base/files/file_posix.cc \
    base/files/file_tracing.cc \
    base/files/file_util.cc \
    base/files/file_util_posix.cc \
    base/files/important_file_writer.cc \
    base/files/memory_mapped_file.cc \
    base/files/memory_mapped_file_posix.cc \
    base/files/scoped_file.cc \
    base/files/scoped_temp_dir.cc \
    base/guid.cc \
    base/hash.cc \
    base/json/json_file_value_serializer.cc \
    base/json/json_parser.cc \
    base/json/json_reader.cc \
    base/json/json_string_value_serializer.cc \
    base/json/json_value_converter.cc \
    base/json/json_writer.cc \
    base/json/string_escape.cc \
    base/lazy_instance.cc \
    base/location.cc \
    base/logging.cc \
    base/md5.cc \
    base/memory/aligned_memory.cc \
    base/memory/ref_counted.cc \
    base/memory/ref_counted_memory.cc \
    base/memory/singleton.cc \
    base/memory/weak_ptr.cc \
    base/message_loop/incoming_task_queue.cc \
    base/message_loop/message_loop.cc \
    base/message_loop/message_loop_task_runner.cc \
    base/message_loop/message_pump.cc \
    base/message_loop/message_pump_default.cc \
    base/message_loop/message_pump_libevent.cc \
    base/metrics/bucket_ranges.cc \
    base/metrics/field_trial.cc \
    base/metrics/metrics_hashes.cc \
    base/metrics/histogram_base.cc \
    base/metrics/histogram.cc \
    base/metrics/histogram_samples.cc \
    base/metrics/histogram_snapshot_manager.cc \
    base/metrics/persistent_histogram_allocator.cc \
    base/metrics/persistent_memory_allocator.cc \
    base/metrics/persistent_sample_map.cc \
    base/metrics/sample_map.cc \
    base/metrics/sample_vector.cc \
    base/metrics/sparse_histogram.cc \
    base/metrics/statistics_recorder.cc \
    base/pending_task.cc \
    base/pickle.cc \
    base/posix/file_descriptor_shuffle.cc \
    base/posix/safe_strerror.cc \
    base/process/kill.cc \
    base/process/kill_posix.cc \
    base/process/launch.cc \
    base/process/launch_posix.cc \
    base/process/process_handle.cc \
    base/process/process_handle_posix.cc \
    base/process/process_iterator.cc \
    base/process/process_metrics.cc \
    base/process/process_metrics_posix.cc \
    base/process/process_posix.cc \
    base/profiler/scoped_profile.cc \
    base/profiler/scoped_tracker.cc \
    base/profiler/tracked_time.cc \
    base/rand_util.cc \
    base/rand_util_posix.cc \
    base/run_loop.cc \
    base/sequence_checker_impl.cc \
    base/sequenced_task_runner.cc \
    base/sha1_portable.cc \
    base/strings/pattern.cc \
    base/strings/safe_sprintf.cc \
    base/strings/string16.cc \
    base/strings/string_number_conversions.cc \
    base/strings/string_piece.cc \
    base/strings/stringprintf.cc \
    base/strings/string_split.cc \
    base/strings/string_util.cc \
    base/strings/string_util_constants.cc \
    base/strings/utf_string_conversions.cc \
    base/strings/utf_string_conversion_utils.cc \
    base/synchronization/cancellation_flag.cc \
    base/synchronization/condition_variable_posix.cc \
    base/synchronization/lock.cc \
    base/synchronization/lock_impl_posix.cc \
    base/synchronization/read_write_lock_posix.cc \
    base/synchronization/waitable_event_posix.cc \
    base/sync_socket_posix.cc \
    base/sys_info.cc \
    base/sys_info_posix.cc \
    base/task/cancelable_task_tracker.cc \
    base/task_runner.cc \
    base/task_scheduler/scheduler_lock_impl.cc \
    base/task_scheduler/sequence.cc \
    base/task_scheduler/sequence_sort_key.cc \
    base/task_scheduler/task.cc \
    base/task_scheduler/task_traits.cc \
    base/test/trace_event_analyzer.cc \
    base/third_party/icu/icu_utf.cc \
    base/third_party/nspr/prtime.cc \
    base/threading/non_thread_safe_impl.cc \
    base/threading/platform_thread_posix.cc \
    base/threading/post_task_and_reply_impl.cc \
    base/threading/sequenced_task_runner_handle.cc \
    base/threading/sequenced_worker_pool.cc \
    base/threading/simple_thread.cc \
    base/threading/thread.cc \
    base/threading/thread_checker_impl.cc \
    base/threading/thread_collision_warner.cc \
    base/threading/thread_id_name_manager.cc \
    base/threading/thread_local_posix.cc \
    base/threading/thread_local_storage.cc \
    base/threading/thread_local_storage_posix.cc \
    base/threading/thread_restrictions.cc \
    base/threading/thread_task_runner_handle.cc \
    base/threading/worker_pool.cc \
    base/threading/worker_pool_posix.cc \
    base/time/clock.cc \
    base/time/default_clock.cc \
    base/time/default_tick_clock.cc \
    base/time/tick_clock.cc \
    base/time/time.cc \
    base/time/time_posix.cc \
    base/timer/elapsed_timer.cc \
    base/timer/timer.cc \
    base/trace_event/heap_profiler_allocation_context.cc \
    base/trace_event/heap_profiler_allocation_context_tracker.cc \
    base/trace_event/heap_profiler_allocation_register.cc \
    base/trace_event/heap_profiler_allocation_register_posix.cc \
    base/trace_event/heap_profiler_heap_dump_writer.cc \
    base/trace_event/heap_profiler_stack_frame_deduplicator.cc \
    base/trace_event/heap_profiler_type_name_deduplicator.cc \
    base/trace_event/malloc_dump_provider.cc \
    base/trace_event/memory_allocator_dump.cc \
    base/trace_event/memory_allocator_dump_guid.cc \
    base/trace_event/memory_dump_manager.cc \
    base/trace_event/memory_dump_request_args.cc \
    base/trace_event/memory_dump_session_state.cc \
    base/trace_event/memory_infra_background_whitelist.cc \
    base/trace_event/process_memory_dump.cc \
    base/trace_event/process_memory_maps.cc \
    base/trace_event/process_memory_totals.cc \
    base/trace_event/trace_buffer.cc \
    base/trace_event/trace_config.cc \
    base/trace_event/trace_event_argument.cc \
    base/trace_event/trace_event_impl.cc \
    base/trace_event/trace_event_memory_overhead.cc \
    base/trace_event/trace_event_synthetic_delay.cc \
    base/trace_event/trace_log.cc \
    base/trace_event/trace_log_constants.cc \
    base/trace_event/trace_sampling_thread.cc \
    base/tracked_objects.cc \
    base/tracking_info.cc \
    base/values.cc \
    base/version.cc \
    base/vlog.cc

libchrome_linux_la_SOURCES :=  base/files/file_path_watcher_linux.cc \
    base/files/file_util_linux.cc \
    base/memory/shared_memory_posix.cc \
    base/posix/unix_domain_socket_linux.cc \
    base/process/internal_linux.cc \
    base/process/process_handle_linux.cc \
    base/process/process_iterator_linux.cc \
    base/process/process_metrics_linux.cc \
    base/strings/sys_string_conversions_posix.cc \
    base/sys_info_linux.cc \
    base/threading/platform_thread_internal_posix.cc \
    base/threading/platform_thread_linux.cc \
    components/timers/alarm_timer_chromeos.cc

libchrome_test_la_SOURCES := \
        base/test/simple_test_clock.cc \
        base/test/simple_test_tick_clock.cc \
        base/test/test_file_util.cc \
        base/test/test_file_util_linux.cc \
        base/test/test_switches.cc \
        base/test/test_timeouts.cc

libchrome_android_la_SOURCES := \
     base/memory/shared_memory_android.cc \
     base/sys_info_chromeos.cc

library_includedir := $(pkgincludedir)


if USE_GLIB
libchrome_la_CFLAGS := $(AM_CFLAGS) -DUSE_GLIB @GLIB_CFLAGS@
libchrome_la_CPPFLAGS := $(AM_CPPFLAGS) -DUSE_GLIB @GLIB_CFLAGS@
libchrome_la_LIBADD := -lm -lbase -lpthread -lcutils -llog -levent @GLIB_LIBS@
libchrome__la_LDFLAGS := -all-static
else
libchrome_la_CFLAGS := $(AM_CFLAGS)
libchrome_la_CPPFLAGS := $(AM_CPPFLAGS)
libchrome_la_LIBADD := -lm -levent -lpthread -lcutils -llog
endif
libchrome_la_SOURCES := $(libchrome_common_la_SOURCES)
libchrome_la_SOURCES += $(libchrome_linux_la_SOURCES)
libchrome_la_SOURCES += $(libchrome_android_la_SOURCES)
libchrome_la_SOURCES += $(libchrome_test_la_SOURCES)
libchrome_la_SOURCES += $(libevent_chrome_la_SOURCES)

