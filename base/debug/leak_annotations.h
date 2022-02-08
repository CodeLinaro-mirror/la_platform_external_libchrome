// Copyright (c) 2011 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef BASE_DEBUG_LEAK_ANNOTATIONS_H_
#define BASE_DEBUG_LEAK_ANNOTATIONS_H_

#include "base/macros.h"
#include "build/build_config.h"

// This file defines macros which can be used to annotate intentional memory
// leaks. Support for annotations is implemented in LeakSanitizer. Annotated
// objects will be treated as a source of live pointers, i.e. any heap objects
// reachable by following pointers from an annotated object will not be
// reported as leaks.
//
// ANNOTATE_SCOPED_MEMORY_LEAK: all allocations made in the current scope
// will be annotated as leaks.
// ANNOTATE_LEAKING_OBJECT_PTR(X): the heap object referenced by pointer X will
// be annotated as a leak.


#define ANNOTATE_SCOPED_MEMORY_LEAK ((void)0)
#define ANNOTATE_LEAKING_OBJECT_PTR(X) ((void)0)


#endif  // BASE_DEBUG_LEAK_ANNOTATIONS_H_
